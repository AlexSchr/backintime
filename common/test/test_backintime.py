# Back In Time
# Copyright (C) 2016 Taylor Raack
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation,Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

import os
import re
import subprocess
import sys
import unittest
from test import generic
import json

import config



sys.path.append(os.path.join(os.path.dirname(__file__), '..'))


class TestBackInTime(generic.TestCase):
    """main tests for backintime"""

    def setUp(self):
        super(TestBackInTime, self).setUp()

    @unittest.skip("--quiet is broken due to some non-filtered logger output")
    def test_quiet_mode(self):
        output = subprocess.getoutput("python3 backintime.py --quiet")
        self.assertEqual("", output)

    def test_local_snapshot_is_successful(self):
        """end to end test - from BIT initialization through snapshot

        From BIT initialization all the way through successful snapshot on a
        local mount. test one of the highest level interfaces a user could
        work with - the command line ensures that argument parsing,
        functionality, and output all work as expected is NOT intended to
        replace individual method tests, which are incredibly useful as well
        """

        # ensure that we see full diffs of assert output if there are any
        self.maxDiff = None

        # create pristine source directory with single file
        subprocess.getoutput("chmod -R a+rwx /tmp/test && rm -rf /tmp/test")
        os.mkdir('/tmp/test')
        with open('/tmp/test/testfile', 'w') as f:
            f.write('some data')

        # create pristine snapshot directory
        subprocess.getoutput(
            "chmod -R a+rwx /tmp/snapshots && rm -rf /tmp/snapshots")
        os.mkdir('/tmp/snapshots')

        # remove restored directory
        subprocess.getoutput("rm -rf /tmp/restored")

        # install proper destination filesystem structure and verify output
        proc = subprocess.Popen(["./backintime",
                                 "--config",
                                 "test/config",
                                 "--share-path",
                                 self.sharePath,
                                 "check-config",
                                 # do not overwrite users crontab
                                 "--no-crontab"],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)

        output, error = proc.communicate()
        msg = 'Returncode: {}\nstderr: {}\nstdout: {}' \
              .format(proc.returncode, error.decode(), output.decode())

        self.assertEqual(proc.returncode, 0, msg)

        self.assertRegex(output.decode(), re.compile(r'''
Back In Time
Version: \d+.\d+.\d+.*

Back In Time comes with ABSOLUTELY NO WARRANTY.
This is free software, and you are welcome to redistribute it
under certain conditions; type `backintime --license' for details.

(INFO: Update to config version \d+
)?
 \+--------------------------------\+
 |  Check/prepair snapshot path   |
 \+--------------------------------\+
Check/prepair snapshot path: done

 \+--------------------------------\+
 |          Check config          |
 \+--------------------------------\+
Check config: done

Config .*test/config profile 'Main profile' is fine.''', re.MULTILINE))

        # execute backup and verify output
        proc = subprocess.Popen(["./backintime",
                                 "--config", "test/config",
                                 "--share-path", self.sharePath,
                                 "backup"],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        output, error = proc.communicate()
        msg = 'Returncode: {}\nstderr: {}\nstdout: {}' \
              .format(proc.returncode, error.decode(), output.decode())
        self.assertEqual(proc.returncode, 0, msg)

        self.assertRegex(output.decode(), re.compile(r'''
Back In Time
Version: \d+.\d+.\d+.*

Back In Time comes with ABSOLUTELY NO WARRANTY.
This is free software, and you are welcome to redistribute it
under certain conditions; type `backintime --license' for details.
''', re.MULTILINE))

        # The log output completely goes to stderr.
        # Note: DBus warnings at the begin and end are already ignored by the regex
        #       but if the BiT serviceHelper.py DBus daemon is not installed
        #       at all the warnings also occur in the middle of below expected
        #       INFO log lines so they are removed by filtering here.
        # TODO If filtering output rows should become a common testing pattern
        #      this code should be refactored into a function for reusability.
        log_output = []
        for line in error.decode().split("\n"):
            if (not line.startswith("WARNING: Failed to connect to Udev serviceHelper")
                    and not line.startswith("WARNING: D-Bus message:")
                    and not line.startswith("WARNING: Udev-based profiles cannot be changed or checked")
                    and not line.startswith("WARNING: Inhibit Suspend failed")):
                log_output.append(line)
        filtered_log_output = "\n".join(log_output)
        self.assertRegex(filtered_log_output, re.compile(r'''INFO: Lock
INFO: Take a new snapshot. Profile: 1 Main profile
INFO: Call rsync to take the snapshot
INFO: Save config file
INFO: Save permissions
INFO: Create info file
INFO: Unlock
''', re.MULTILINE))

        # get snapshot id
        subprocess.check_output(["./backintime",
                                 "--config",
                                 "test/config",
                                 "snapshots-list"])

        # execute restore and verify output
        proc = subprocess.Popen(["./backintime",
                                 "--config",
                                 "test/config",
                                 "--share-path",
                                 self.sharePath,
                                 "restore",
                                 "/tmp/test/testfile",
                                 "/tmp/restored",
                                 "0"],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        output, error = proc.communicate()
        msg = 'Returncode: {}\nstderr: {}\nstdout: {}' \
              .format(proc.returncode, error.decode(), output.decode())
        self.assertEqual(proc.returncode, 0, msg)

        self.assertRegex(output.decode(), re.compile(r'''
Back In Time
Version: \d+.\d+.\d+.*

Back In Time comes with ABSOLUTELY NO WARRANTY.
This is free software, and you are welcome to redistribute it
under certain conditions; type `backintime --license' for details.

''', re.MULTILINE))

        # The log output completely goes to stderr
        self.assertRegex(error.decode(), re.compile(r'''INFO: Restore: /tmp/test/testfile to: /tmp/restored.*''',
                                                     re.MULTILINE))

        # verify that files restored are the same as those backed up
        subprocess.check_output(["diff",
                                 "-r",
                                 "/tmp/test",
                                 "/tmp/restored"])

    def test_diagnostics_arg(self):

        # "output" from stdout may currently be polluted with logging output
        # lines from INFO and DEBUG log output.
        # Logging output of WARNING and ERROR is already written to stderr
        # so `check_output` does work here (returns only stdout without stderr).
        output = subprocess.check_output(["./backintime", "--diagnostics"])
        # output = subprocess.getoutput("./backintime --diagnostics")

        diagnostics = json.loads(output)
        self.assertEqual(diagnostics["backintime"]["name"],    config.Config.APP_NAME)
        self.assertEqual(diagnostics["backintime"]["version"], config.Config.VERSION)
