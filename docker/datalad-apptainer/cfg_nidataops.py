#!/usr/bin/env python3
"""Procedure to configure Git annex to add text files directly to Git"""

import sys
import os.path as op

from datalad.distribution.dataset import require_dataset

ds = require_dataset(
    sys.argv[1],
    check_installed=True,
    purpose='configuration')

nthg = {'annex.largefiles': 'nothing'}
anthg = {'annex.largefiles': 'anything'}
annex_largefiles = '((mimeencoding=binary)and(largerthan=0))'
attrs = ds.repo.get_gitattributes('*')
if not attrs.get('*', {}).get(
        'annex.largefiles', None) == annex_largefiles:
    ds.repo.set_gitattributes([
        ('*', {'annex.largefiles': annex_largefiles}),
        ('.gitignore', nthg),
        ('.gitmodules', nthg),
        ('.gitlab-ci.yml', nthg),
        ('.all-contributorsrc', nthg),
        ('.bidsignore', nthg),
        ('*.json', nthg),
        ('*.txt', nthg),
        ('*.tsv', nthg),
        ('*.nii.gz', anthg),
        ('*.tgz', anthg),
        ('*_scans.tsv', anthg),
        # annex event files as they contain subjects behavioral responses
        ('sub-*/**/*_events.tsv', anthg),
        ('*.bk2', anthg),
        ('*.html', anthg),
        ('*.svg', anthg),
        ])

git_attributes_file = op.join(ds.path, '.gitattributes')
ds.save(
    git_attributes_file,
    message="Setup gitattributes for ni-dataops",
    result_renderer='disabled'
)
