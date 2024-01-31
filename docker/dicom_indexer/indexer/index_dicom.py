import os
import pydicom as dicom
import argparse
import pathlib
import urllib.parse
import datalad.api as dlad
import shutil
import gitlab
import tempfile
import logging
import subprocess
import yaml
from contextlib import contextmanager

DEBUG = bool(os.environ.get("DEBUG", False))
if DEBUG:
    logging.basicConfig(level=logging.DEBUG)

GITLAB_REMOTE_NAME = os.environ.get("GITLAB_REMOTE_NAME", "origin")
GITLAB_TOKEN = os.environ.get("GITLAB_TOKEN", None)
GITLAB_BOT_USERNAME = os.environ.get("GITLAB_BOT_USERNAME", None)
BIDS_DEV_BRANCH = os.environ.get("BIDS_DEV_BRANCH", "dev")

S3_REMOTE_DEFAULT_PARAMETERS = [
    "type=S3",
    "encryption=none",
    "autoenable=true",
    "port=443",
    "protocol=https",
    "chunk=1GiB",
    "requeststyle=path",
]


# TODO: rewrite for pathlib.Path input
def sort_series(path: pathlib.Path) -> None:
    """Sort series in separate folder

    Parameters
    ----------
    path : str
      path to dicoms

    """
    files = path.glob(os.path.join(path, "*"))
    for f in files:
        if not os.path.isfile(f):
            continue
        dic = dicom.read_file(f, stop_before_pixels=True)
        # series_number = dic.SeriesNumber
        series_instance_uid = dic.SeriesInstanceUID
        subpath = os.path.join(path, series_instance_uid)
        if not os.path.exists(subpath):
            os.mkdir(subpath)
        os.rename(f, os.path.join(subpath, f.name))


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="dicom_indexer - indexes dicoms into datalad"
    )
    p.add_argument("input", help="path/url of the dicom.")
    p.add_argument(
        "--gitlab-url",
        type=str,
        default=os.environ.get("GITLAB_SERVER", None),
        help="http(s) url to the gitlab server where to push repos",
    )
    p.add_argument(
        "--gitlab-group-template",
        default="{ReferringPhysicianName}/{StudyDescription}",
        type=str,
        help="string with placeholder for dicom tags",
    )
    p.add_argument(
        "--session-name-tag",
        default="PatientName",
        type=str,
        help="dicom tags that contains the name of the session",
    )
    p.add_argument("--storage-remote", help="url to the datalad remote")
    p.add_argument(
        "--sort-series",
        type=bool,
        default=True,
        help="sort dicom series in separate folders",
    )
    p.add_argument(
        "--fake-dates",
        action="store_true",
        help="use fake dates for datalad dataset",
    )
    p.add_argument(
        "--p7z-opts",
        type=str,
        default="-mx5 -ms=off",
        help="option for 7z generated archives",
    )
    return p


def main() -> None:
    parser = _build_arg_parser()
    args = parser.parse_args()

    if not GITLAB_REMOTE_NAME:
        raise RuntimeError("missing GITLAB_REMOTE_NAME env var")
    if not GITLAB_TOKEN:
        raise RuntimeError("missing GITLAB_TOKEN env var")
    if not GITLAB_BOT_USERNAME:
        raise RuntimeError("missing GITLAB_BOT_USERNAME env var")

    input = urllib.parse.urlparse(args.input)
    output_remote = urllib.parse.urlparse(args.storage_remote)
    gitlab_url = urllib.parse.urlparse(args.gitlab_url)

    with index_dicoms(
        input,
        sort_series=args.sort_series,
        fake_dates=args.fake_dates,
        p7z_opts=args.p7z_opts,
    ) as dicom_session_ds:
        session_metas = extract_session_metas(dicom_session_ds)

        if (
            not input.scheme
            or input.scheme == "file"
            or args.force_export
            and output_remote
        ):
            export_data(
                dicom_session_ds,
                output_remote,
                dicom_session_tag=args.session_name_tag,
                session_metas=session_metas,
            )

        setup_gitlab_repos(
            dicom_session_ds,
            gitlab_url=gitlab_url,
            dicom_session_tag=args.session_name_tag,
            session_metas=session_metas,
            gitlab_group_template=args.gitlab_group_template,
        )


@contextmanager
def index_dicoms(
    input: urllib.parse.ParseResult,
    sort_series: bool,
    fake_dates: bool,
    p7z_opts: str,
) -> dlad.Dataset:
    """Process incoming dicoms into datalad repo"""

    with tempfile.TemporaryDirectory(delete=not DEBUG) as tmpdirname:
        dicom_session_ds = dlad.create(tmpdirname, fake_dates=fake_dates)

        if not input.scheme or input.scheme == "file":
            archive = import_local_data(
                dicom_session_ds,
                pathlib.Path(input.path),
                sort_series=sort_series,
                p7z_opts=p7z_opts,
            )
        elif input.scheme in ["http", "https", "s3"]:
            archive = import_remote_data(dicom_session_ds, input_url)

        # index dicoms files
        dlad.add_archive_content(
            archive,
            dataset=dicom_session_ds,
            strip_leading_dirs=True,
            commit=False,
        )
        # cannot pass message above so commit now
        dicom_session_ds.save(message=f"index dicoms from archive {archive}")  #
        # optimize git index after large import
        dicom_session_ds.repo.gc()  # aggressive by default
        yield dicom_session_ds


def export_data(
    dicom_session_ds: dlad.Dataset,
    output_remote: urllib.parse.ParseResult,
    dicom_session_tag: str,
    session_metas: dict,
) -> None:
    if "ria" in output_remote.scheme:
        export_to_ria(
            dicom_session_ds,
            output_remote,
            dicom_session_tag=dicom_session_tag,
            session_metas=session_metas,
        )
    elif output_remote.scheme == "s3":
        export_to_s3(dicom_session_ds, output_remote, session_metas)


def set_bot_privileges(gitlab_conn: gitlab.Gitlab, gitlab_group_path: pathlib.Path) -> None:
    # add maint permissions for the dicom bot user on the study repos
    study_group = get_or_create_gitlab_group(gitlab_conn, gitlab_group_path)
    bot_user = gitlab_conn.users.list(username=GITLAB_BOT_USERNAME)
    if not bot_user:
        raise RuntimeError(
            f"bot_user: {GITLAB_BOT_USERNAME} does not exists in gitlab instance"
        )
    bot_user = bot_user[0]
    if not any(m.id == bot_user.id for m in study_group.members.list()):
        study_group.members.create(
            {
                "user_id": bot_user.id,
                "access_level": gitlab.const.AccessLevel.MAINTAINER,
            }
        )


def setup_gitlab_repos(
    dicom_session_ds: dlad.Dataset,
    gitlab_url: urllib.parse.ParseResult,
    session_metas: dict,
    dicom_session_tag: str,
    gitlab_group_template: str,
) -> None:
    gitlab_conn = connect_gitlab(gitlab_url)

    # generate gitlab group/repo paths
    gitlab_group_path = pathlib.Path(gitlab_group_template.format(**session_metas))
    dicom_sourcedata_path = gitlab_group_path / "sourcedata/dicoms"
    dicom_session_path = dicom_sourcedata_path / session_metas["StudyInstanceUID"]
    dicom_study_path = dicom_sourcedata_path / "study"

    # create repo (should not exists unless rerun)
    dicom_session_repo = get_or_create_gitlab_project(gitlab_conn, dicom_session_path)
    dicom_session_ds.siblings(
        action="configure",  # allow to overwrite existing config
        name=GITLAB_REMOTE_NAME,
        url=dicom_session_repo._attrs["ssh_url_to_repo"],
    )
    """
    # prevent warnings
    dicom_session_ds.config.add(
        f"remote.{GITLAB_REMOTE_NAME}.annex-ignore",
        value='false',
        scope='local'
    )"""

    set_bot_privileges(gitlab_conn, gitlab_group_path)
    # and push
    dicom_session_ds.push(to=GITLAB_REMOTE_NAME)

    ## add the session to the dicom study repo
    dicom_study_repo = get_or_create_gitlab_project(gitlab_conn, dicom_study_path)
    with tempfile.TemporaryDirectory(delete=not DEBUG) as tmpdir:
        dicom_study_ds = dlad.install(
            source=dicom_study_repo._attrs["ssh_url_to_repo"],
            path=tmpdir,
        )
        """
        # prevent warnings when pushing
        dicom_study_ds.config.add(
            f"remote.origin.annex-ignore",
            value='false',
            scope='local'
        )"""

        if dicom_study_ds.repo.get_hexsha() is None or dicom_study_ds.id is None:
            dicom_study_ds.create(force=True)
            # add default study DS structure.
            init_dicom_study(dicom_study_ds, gitlab_group_path)
            # initialize BIDS project
            init_bids(gitlab_conn, dicom_study_repo, gitlab_group_path)
            # create subgroup for QC and derivatives repos
            get_or_create_gitlab_group(gitlab_conn, gitlab_group_path / "derivatives")
            get_or_create_gitlab_group(gitlab_conn, gitlab_group_path / "qc")

        dicom_study_ds.install(
            source=dicom_session_repo._attrs["ssh_url_to_repo"],
            path=session_metas.get(dicom_session_tag),
        )

        # Push to gitlab
        dicom_study_ds.push(to="origin")


def init_bids(
    gl: gitlab.Gitlab,
    dicom_study_repo: dlad.Dataset,
    gitlab_group_path: pathlib.Path,
) -> None:
    bids_project_repo = get_or_create_gitlab_project(gl, gitlab_group_path / "bids")
    with tempfile.TemporaryDirectory() as tmpdir:
        bids_project_ds = dlad.install(
            source=bids_project_repo._attrs["ssh_url_to_repo"],
            path=tmpdir,
        )
        bids_project_ds.create(force=True)
        shutil.copytree("repo_templates/bids", bids_project_ds.path, dirs_exist_ok=True)
        bids_project_ds.save(path=".", message="init structure and pipelines")
        bids_project_ds.install(
            path="sourcedata/dicoms",
            source=dicom_study_repo._attrs["ssh_url_to_repo"],
        )
        # TODO: setup sensitive / non-sensitive S3 buckets
        bids_project_ds.push(to="origin")
        # create dev branch and push for merge requests
        bids_project_ds.repo.checkout(BIDS_DEV_BRANCH, ["-b"])
        bids_project_ds.push(to="origin")
        # set protected branches
        bids_project_repo.protectedbranches.create(data={"name": "convert/*"})
        bids_project_repo.protectedbranches.create(data={"name": "dev"})


def init_dicom_study(
    dicom_study_ds: dlad.Dataset,
    gitlab_group_path: pathlib.Path,
) -> None:
    shutil.copytree(
        "repo_templates/dicom_study", dicom_study_ds.path, dirs_exist_ok=True
    )
    env = {
        "variables": {
            "STUDY_PATH": str(gitlab_group_path),
            "BIDS_PATH": str(gitlab_group_path / "bids"),
        }
    }
    with (pathlib.Path(dicom_study_ds.path) / "ci-env.yml").open("w") as outfile:
        yaml.dump(env, outfile, default_flow_style=False)
    dicom_study_ds.save(path=".", message="init structure and pipelines")
    dicom_study_ds.push(to="origin")


SESSION_META_KEYS = [
    "StudyInstanceUID",
    "PatientID",
    "PatientName",
    "ReferringPhysicianName",
    "StudyDate",
    "StudyDescription",
]


def extract_session_metas(dicom_session_ds: dlad.Dataset) -> dict:
    all_files = dicom_session_ds.repo.get_files()
    for f in all_files:
        try:
            dic = dicom.read_file(dicom_session_ds.pathobj / f, stop_before_pixels=True)
        except Exception as e:  # TODO: what exception occurs when non-dicom ?
            continue
        # return at first dicom found
        return {k: str(getattr(dic, k)).replace("^", "/") for k in SESSION_META_KEYS}
    raise InputError("no dicom found")


def import_local_data(
    dicom_session_ds: dlad.Dataset,
    input_path: pathlib.Path,
    sort_series: bool = True,
    p7z_opts: str = "-mx5 -ms=off",
):
    dest = input_path.name

    if input_path.is_dir():
        dest = dest + ".7z"
        # create 7z archive with 1block/file parameters
        cmd = ["7z", "u", str(dest), str(input_path)] + p7z_opts.split()
        subprocess.run(cmd, cwd=dicom_session_ds.path)
    elif input_path.is_file():
        dest = dicom_session_ds.pathobj / dest
        try:  # try hard-linking to avoid copying
            os.link(str(input_path), str(dest))
        except OSError:  # fallback if hard-linking not supported
            shutil.copyfile(str(input_path), str(dest))
    dicom_session_ds.save(dest, message="add dicoms archive")
    return dest


def import_remote_data(
    dicom_session_ds: dlad.Dataset, input_url: urllib.parse.ParseResult
):
    try:
        dest = pathlib.Path(url.path).name
        dicom_session_ds.repo.add_url_to_file(dest, url)
    except Exception:
        ...  # TODO: check how things can fail here and deal with it.
    return dest


def export_to_ria(
    ds: dlad.Dataset,
    ria_url: urllib.parse.ParseResult,
    dicom_session_tag: str,
    session_metas: dict,
    export_ria_archive: bool = False,
    ria_archive_7zopts: str = "-mx5 -ms=off",
):
    ria_name = pathlib.Path(ria_url.path).name
    ds.create_sibling_ria(
        ria_url.geturl(),
        name=ria_name,
        alias=session_metas[dicom_session_tag],
        existing="reconfigure",
        new_store_ok=True,
    )
    ds.push(to=ria_name, data="nothing")

    # keep the old ria-archive before add-archive-content, not used for now
    if export_ria_archive:
        ria_sibling_path = pathlib.Path(ds.siblings(name=ria_name)[0]["url"])
        archive_path = ria_sibling_path / "archives" / "archive.7z"
        ds.export_archive_ora(
            archive_path,
            opts=ria_archive_7zopts.split(),
            missing_content="error",
        )
        ds.repo.fsck(remote=f"{ria_url}-storage", fast=True)  # index
        ds.push(to=ria_name, data="nothing")


def export_to_s3(
    ds: dlad.Dataset,
    s3_url: urllib.parse.ParseResult,
    session_metas: dict,
):
    # TODO: check if we can reuse a single bucket (or per study) with fileprefix
    # git-annex initremote remotename ...
    remote_name = s3_url.hostname
    _, bucket_name, *fileprefix = pathlib.Path(s3_url.path).parts
    fileprefix.append(session_metas["StudyInstanceUID"] + "/")
    ds.repo.init_remote(
        remote_name,
        S3_REMOTE_DEFAULT_PARAMETERS
        + [
            f"host={s3_url.hostname}",
            f"bucket={bucket_name}",
            f"fileprefix={'/'.join(fileprefix)}",
        ],
    )
    ds.repo.set_preferred_content(
        "wanted",
        "include=*7z or include=*.tar.gz or include=*zip",
        remote=remote_name,
    )

    ds.push(to=remote_name, data="auto")
    # It does not push the data to the S3 unless I set data="anything" which pushes everyhing including the deflated archived data


def connect_gitlab(
    gitlab_url: urllib.parse.ParseResult, debug: bool = False
) -> gitlab.Gitlab:
    """
    Connection to Gitlab
    """
    gl = gitlab.Gitlab(gitlab_url.geturl(), private_token=GITLAB_TOKEN)
    if debug:
        gl.enable_debug()
    gl.auth()
    return gl


def get_or_create_gitlab_group(
    gl: gitlab.Gitlab,
    group_path: pathlib.Path,
):
    """fetch or create a gitlab group"""
    group_list = group_path.parts
    found = False
    for keep_groups in reversed(range(len(group_list) + 1)):
        tmp_repo_path = "/".join(group_list[0:keep_groups])
        logging.debug(tmp_repo_path)
        gs = gl.groups.list(search=tmp_repo_path)
        for g in gs:
            if g.full_path == tmp_repo_path:
                found = True
                break
        if found:
            break
    for nb_groups in range(keep_groups, len(group_list)):
        if nb_groups == 0:
            logging.debug(f"Creating group {group_list[nb_groups]}")
            g = gl.groups.create(
                {"name": group_list[nb_groups], "path": group_list[nb_groups]}
            )
        else:
            logging.debug(f"Creating group {group_list[nb_groups]} from {g.name}")
            g = gl.groups.create(
                {
                    "name": group_list[nb_groups],
                    "path": group_list[nb_groups],
                    "parent_id": g.id,
                }
            )

    return g


def get_or_create_gitlab_project(gl: gitlab.Gitlab, project_path: pathlib.Path):
    """fetch or create a gitlab repo"""
    project_name = project_path.parts

    # Look for exact repo/project:
    p = gl.projects.list(search=project_name[-1])
    if p:
        for curr_p in p:
            if curr_p.path_with_namespace == str(project_path):
                return curr_p

    g = get_or_create_gitlab_group(gl, project_path.parent)
    logging.debug(f"Creating project {project_name[-1]} from {g.name}")
    p = gl.projects.create({"name": project_name[-1], "namespace_id": g.id})
    return p


if __name__ == "__main__":
    main()
