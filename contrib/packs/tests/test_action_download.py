#!/usr/bin/env python

# Licensed to the StackStorm, Inc ('StackStorm') under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import mock
import os
import shutil
import tempfile
import hashlib

from git.repo import Repo
from gitdb.exc import BadName
from st2common.services import packs as pack_service
from st2tests.base import BaseActionTestCase

from pack_mgmt.download import DownloadGitRepoAction

PACK_INDEX = {
    "test": {
        "version": "0.4",
        "name": "test",
        "repo_url": "https://github.com/StackStorm-Exchange/stackstorm-test",
        "author": "st2-dev",
        "keywords": ["some", "search", "another", "terms"],
        "email": "info@stackstorm.com",
        "description": "st2 pack to test package management pipeline"
    },
    "test2": {
        "version": "0.5",
        "name": "test2",
        "repo_url": "https://github.com/StackStorm-Exchange/stackstorm-test2",
        "author": "stanley",
        "keywords": ["some", "special", "terms"],
        "email": "info@stackstorm.com",
        "description": "another st2 pack to test package management pipeline"
    }
}


@mock.patch.object(pack_service, 'fetch_pack_index', mock.MagicMock(return_value=(PACK_INDEX, {})))
class DownloadGitRepoActionTestCase(BaseActionTestCase):
    action_cls = DownloadGitRepoAction

    def setUp(self):
        super(DownloadGitRepoActionTestCase, self).setUp()

        clone_from = mock.patch.object(Repo, 'clone_from')

        self.addCleanup(clone_from.stop)
        self.clone_from = clone_from.start()

        expand_user = mock.patch.object(os.path, 'expanduser',
                                        mock.MagicMock(return_value=tempfile.mkdtemp()))

        self.addCleanup(expand_user.stop)
        self.expand_user = expand_user.start()

        self.repo_base = tempfile.mkdtemp()

        self.repo_instance = mock.MagicMock()

        def side_effect(url, to_path, **kwargs):
            # Since we have no way to pass pack name here, we would have to derive it from repo url
            fixture_name = url.split('/')[-1]
            fixture_path = os.path.join(self._get_base_pack_path(), 'tests/fixtures', fixture_name)
            shutil.copytree(fixture_path, to_path)
            return self.repo_instance

        self.clone_from.side_effect = side_effect

    def tearDown(self):
        shutil.rmtree(self.repo_base)
        shutil.rmtree(self.expand_user())

    def test_run_pack_download(self):
        action = self.get_action_instance()
        result = action.run(packs=['test'], abs_repo_base=self.repo_base)
        temp_dir = hashlib.md5(PACK_INDEX['test']['repo_url']).hexdigest()

        self.assertEqual(result, {'test': 'Success.'})
        self.clone_from.assert_called_once_with(PACK_INDEX['test']['repo_url'],
                                                os.path.join(os.path.expanduser('~'), temp_dir))
        self.assertTrue(os.path.isfile(os.path.join(self.repo_base, 'test/pack.yaml')))

    def test_run_pack_download_existing_pack(self):
        action = self.get_action_instance()
        action.run(packs=['test'], abs_repo_base=self.repo_base)
        self.assertTrue(os.path.isfile(os.path.join(self.repo_base, 'test/pack.yaml')))

        result = action.run(packs=['test'], abs_repo_base=self.repo_base)

        self.assertEqual(result, {'test': 'Success.'})

    def test_run_pack_download_multiple_packs(self):
        action = self.get_action_instance()
        result = action.run(packs=['test', 'test2'], abs_repo_base=self.repo_base)
        temp_dirs = [
            hashlib.md5(PACK_INDEX['test']['repo_url']).hexdigest(),
            hashlib.md5(PACK_INDEX['test2']['repo_url']).hexdigest()
        ]

        self.assertEqual(result, {'test': 'Success.', 'test2': 'Success.'})
        self.clone_from.assert_any_call(PACK_INDEX['test']['repo_url'],
                                        os.path.join(os.path.expanduser('~'), temp_dirs[0]))
        self.clone_from.assert_any_call(PACK_INDEX['test2']['repo_url'],
                                        os.path.join(os.path.expanduser('~'), temp_dirs[1]))
        self.assertEqual(self.clone_from.call_count, 2)
        self.assertTrue(os.path.isfile(os.path.join(self.repo_base, 'test/pack.yaml')))
        self.assertTrue(os.path.isfile(os.path.join(self.repo_base, 'test2/pack.yaml')))

    @mock.patch.object(Repo, 'clone_from')
    def test_run_pack_download_error(self, clone_from):
        clone_from.side_effect = Exception('Something went terribly wrong during the clone')

        action = self.get_action_instance()
        self.assertRaises(Exception, action.run, packs=['test'], abs_repo_base=self.repo_base)

    def test_run_pack_download_no_tag(self):
        self.repo_instance.commit.side_effect = BadName

        action = self.get_action_instance()
        self.assertRaises(ValueError, action.run, packs=['test=1.2.3'],
                          abs_repo_base=self.repo_base)

    def test_run_pack_download_v_tag(self):
        def side_effect(ref):
            if ref[0] != 'v':
                raise BadName()
            return mock.MagicMock(hexsha='abcdef')

        self.repo_instance.commit.side_effect = side_effect
        self.repo_instance.git = mock.MagicMock(
            branch=(lambda *args: 'master'),
            checkout=(lambda *args: True)
        )

        action = self.get_action_instance()
        result = action.run(packs=['test=1.2.3'], abs_repo_base=self.repo_base)

        self.assertEqual(result, {'test': 'Success.'})
