import os
import dicom
import argparse
import pathlib
import urllib.parse
import datalad.api as dlad
import shutil


GITLAB_REMOTE_NAME = os.environ.get('GITLAB_REMOTE_NAME', 'gitlab')

def sort_series(path: str) -> None:
    """Sort series in separate folder

    Parameters
    ----------
    path : str
      path to dicoms

    """
    files = glob.glob(os.path.join(path, '*'))
    for f in files:
        if not os.path.isfile(f):
            continue
        dic = dicom.read_file(f, stop_before_pixels=True)
        # series_number = dic.SeriesNumber
        series_instance_uid = dic.SeriesInstanceUID
        subpath = os.path.join(path, series_instance_uid)
        if not os.path.exists(subpath):
            os.mkdir(subpath)
        os.rename(f, os.path.join(subpath, os.path.basename(f)))


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="dicom_indexer - indexes dicoms into datalad")
    p.add_argument(
        'input', nargs='+',
        help='path/url of the dicom.')
    p.add_argument()
    p.add_argument(
        'gitlab_group_template',
        default='{ReferringPhysicianName}/{StudyDescription.replace('^','/')}'
        type=str)
    p.add_argument(
        '--storage-remote',
        help='url to the datalad remote')
    p.add_argument(
        "--sort-series",
        action="store_true",
        type=bool,
        default=True,
        help="sort dicom series in separate folders",
    )
    p.add_argument(
        "--fake-dates",
        type=bool,
        action="store_true",
        help="use fake dates for datalad dataset",
    )
    return p

def main() -> None:

    parser = _build_arg_parser()
    args = parser.parse_args()

    input = urllib.parse.urlparse(args.input)
    output_remote = urllib.parse.urlparse(args.storage_remote)
    logger.info(f"input data: {input}")

    process(
        input,
        output_remote,
        sort_series=p.sort_series,
        fake_dates=p.fake_dates,
    )

def process(
    input:urllib.parse.ParseResult,
    output_remote: urllib.parse.ParseResult,
    sort_series: bool,
    fake_dates: bool,
    p7z_opts: str,
    gitlab_url: urllib.parse.ParseResult,
    gitlab_group_template: str,
    force_export: bool=False,
) -> None:
    """Process incoming dicoms into datalad repo

    """
    with tempfile.TemporaryDirectory() as tmpdirname:
        dicom_session_ds = dlad.create(tmpdirname, fake_dates=fake_dates)

        do_export = force_export

        if not input.scheme or input.scheme == 'file':
            dest = import_local_data(
                dicom_session_ds,
                pathlib.Path(input.path),
                sort_series=sort_series,
                p7z_opts=p7z_opts,
            )
            do_export = True
        elif input.scheme in ['http', 'https', 's3']:
            dest = import_remote_data(dicom_session_ds, input_url)

        # index dicoms files
        dicom_session_ds.add_archive_content(
            dest,
            strip_leading_dirs=True,
            commit=False,
        )
        # cannot pass message above so commit now
        dicom_session_ds.save(message='index dicoms from archive')#
        # optimize git index after large import
        dicom_session_ds.repo.gc() # aggressive by default

        session_metas = extract_session_metas(dicom_session_ds)

        if do_export:
            if output_remote.scheme == 'ria':
                export_to_ria(dicom_session_ds, output_remote, session_metas)
            elif output_remote.scheme == 's3':
                export_to_s3(dicom_session_ds, output_remote, session_metas)


        setup_gitlab_remote(dicom_session_ds, gitlab_url, session_metas)





def setup_gitlab_repos(
    dicom_session_ds: dlad.Dataset,
    gitlab_url: urllib.parse.ParseResult,
    session_metas: dict,
):
    gitlab_conn = connect_gitlab()

    gitlab_group_path = gitlab_group_template.format(session_metas)
    dicom_sourcedata_path = '/'.join([dicom_session_path, 'sourcedata/dicoms'])
    dicom_session_path = '/'.join([dicom_sourcedata_path, ['StudyInstanceUID']])
    dicom_study_path = '/'.join([dicom_sourcedata_path, 'study'])

    dicom_session_repo = get_or_create_gitlab_project(gl, dicom_session_path)
    ds.siblings(
        action='configure', # allow to overwrite existing config
        name=GITLAB_REMOTE_NAME,
        url=dicom_session_repo._attrs['ssh_url_to_repo'],
    )
    ds.push(to=GITLAB_REMOTE_NAME)

    study_group = get_or_create_group(gl, gitlab_group_path)
    bot_user = gl.users.list(username=GITLAB_BOT_USERNAME)[0]
    study_group.members.create({
        'user_id': bot_user.id,
        'access_level': gitlab.const.AccessLevel.MAINTAINER,
        })


    dicom_study_repo = get_or_create_project(gl, dicom_study_path)
    with tempfile.TemporaryDirectory() as tmpdir:
        dicom_study_ds = datalad.api.install(
            source = dicom_study_repo._attrs['ssh_url_to_repo'],
            path=tmpdir,
            )

        if dicom_study_ds.repo.get_hexsha() is None or dicom_study_ds.id is None:
            dicom_study_ds.create(force=True)
            dicom_study_ds.push(to='origin')
            # add default study DS structure.
            init_dicom_study(dicom_study_ds, PI, study_name)
            # initialize BIDS project
            init_bids(gl, PI, study_name, dicom_study_repo)
            create_group(gl, [PI, study_name, "derivatives"])
            create_group(gl, [PI, study_name, "qc"])

        dicom_study_ds.install(
            source=dicom_session_repo._attrs['ssh_url_to_repo'],
            path=session_meta['PatientName'],
            )
        dicom_study_ds.create_sibling_ria(
            UNF_DICOMS_RIA_URL,
            name=UNF_DICOMS_RIA_NAME,
            alias=study_name,
            existing='reconfigure')


        # Push to gitlab + local ria-store
        dicom_study_ds.push(to='origin')
        dicom_study_ds.push(to=UNF_DICOMS_RIA_NAME)


SESSION_META_KEYS = [
    'StudyInstanceUID',
    'PatientID',
    'PatientName',
    'ReferringPhysicianName',
    'StudyDate',
    'StudyDescription',
]

def extract_session_metas(dicom_session_ds: dlad.Dataset):
    all_files = dicom_session_ds.repo.find('*')
    for f in all_files:
        try:
            dic = dicom.read_file(f, stop_before_pixels=True)
        except Exception: # TODO: what exception occurs when non-dicom ?
            continue
        # return at first dicom found
        return {k:getattr(dic, k) for k in SESSION_META_KEYS}


def import_local_data(
    dicom_session_ds: dlad.Dataset,
    input_path: pathlib.Path,
    sort_series: bool=True,
    p7z_opts: str='-mx5'
):
    dest = input_path.basename()

    if input_path.is_dir():
        dest = dest + '.7z'
        # create 7z archive with 1block/file parameters
        subprocess.run(
                ['7z', 'u', str(dest), '.'] + p7z_opts,
                cwd=str(dicom_session_ds.path),
            )
    elif input_path.is_file():
        dest = dicom_session_ds.path / dest
        try: # try hard-linking to avoid copying
            os.link(str(input_path), str(dest))
        except OSError: #fallback if hard-linking not supported
            shutil.copyfile(str(input_path), str(dest))
    dicom_session_ds.save(dest, message='add dicoms archive')
    return dest


def import_remote_data(
    dicom_session_ds:dlad.Dataset,
    input_url:urllib.parse.ParseResult):

    try:
        dest = pathlib.Path(url.path).basename
        dicom_session_ds.repo.add_url_to_file(dest, url)
    except Exception:
        ... #TODO: check how things can fail here and deal with it.
    return dest



def export_to_ria(
    ds: dlad.Dataset,
    ria_url:urllib.parse.ParseResult,
    session_metas: dict,
):
    ria_name = pathlib.Path(ria_url.path).basename
    ds.create_sibling_ria(
        ria_url,
        name=ria_name,
        alias=session_meta['PatientID'],
        existing='reconfigure')
    ds.push(to=ria_name, data='nothing')
    ria_sibling_path = pathlib.Path(ds.siblings(name=ria_name)[0]['url'])
    archive_path = ria_sibling_path / 'archives' / 'archive.7z'
    ds.export_archive_ora(
        archive_path,
        opts=[f'-mx{COMPRESSION_LEVEL}'],
        missing_content='error')
    ds.repo.fsck(remote=f"{ria_url}-storage", fast=True) #index
    ds.push(to=ria_name, data='nothing')

def export_to_s3(
    ds: dlad.Dataset,
    s3_url:urllib.parse.ParseResult,
    session_metas: dict,
):
    ...
    # git-annex initremote remotename ...
    # git-annex wanted remotename include=**.{7z,tar.gz,zip}
    # datalad push --data auto --to remotename


def connect_gitlab(debug=False):
    """
    Connection to Gitlab
    """
    gl = gitlab.Gitlab(GITLAB_SERVER, private_token=GITLAB_TOKEN)
    if debug:
        gl.enable_debug()
    gl.auth()
    return gl


def get_or_create_gitlab_group(gl, group_list):
    """
    """
    found = False
    for keep_groups in reversed(range(len(group_list)+1)):
        tmp_repo_path = '/'.join(group_list[0:keep_groups])
        logging.warning(tmp_repo_path)
        gs = gl.groups.list(search=tmp_repo_path)
        for g in gs:
             if g.full_path == tmp_repo_path:
                 found = True
                 break
        if found:
            break
    for nb_groups in range(keep_groups, len(group_list)):
        if nb_groups == 0:
            msg = "Creating group {}".format(group_list[nb_groups])
            logging.warning(msg)
            logging.warning(len(msg) * "=")
            g = gl.groups.create({'name': group_list[nb_groups],
                                  'path': group_list[nb_groups]})
        else:
            msg = 'Creating group {} from {}'.format(group_list[nb_groups],
                                                     g.name)
            logging.warning(msg)
            logging.warning(len(msg) * "=")
            g = gl.groups.create({'name': group_list[nb_groups],
                                  'path': group_list[nb_groups],
                                  'parent_id': g.id})

    return g


def get_or_create_gitlab_project(gl, project_name):
    """
    """
    if len(project_name) == 1:
        # Check if exists
        p = gl.projects.list(search=project_name[0])
        if not p:
            p = gl.projects.create({'name': project_name[0],
                                   'path': project_name[0]})
            return p.id
        else:
            return p[0].id

    repo_full_path = '/'.join(project_name)

    # Look for exact repo/project:
    p = gl.projects.list(search=project_name[-1])
    if p:
        for curr_p in p:
            if curr_p.path_with_namespace == repo_full_path:
                return curr_p

    g = get_or_create_gitlab_group(gl, project_name[:-1])
    p = gl.projects.create({'name': project_name[-1],
                           'namespace_id': g.id})
    return p
