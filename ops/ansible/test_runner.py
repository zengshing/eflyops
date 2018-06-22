# -*- coding: utf-8 -*-
#

import unittest
import sys

sys.path.insert(0, "../..")

from ops.ansible.runner import AdHocRunner, CommandRunner, PlayBookRunner
from ops.ansible.inventory import BaseInventory
from ops.ansible.runner import Options 

#class TestAdHocRunner(unittest.TestCase):
#    def setUp(self):
#        host_data = [
#            {
#                "hostname": "testserver",
#                "ip": "192.168.244.168",
#                "port": 22,
#                "username": "root",
#                "password": "redhat",
#            },
#        ]
#        inventory = BaseInventory(host_data)
#        self.runner = AdHocRunner(inventory)
#
#    def test_run(self):
#        tasks = [
#            {"action": {"module": "shell", "args": "ls"}, "name": "run_cmd"},
#            {"action": {"module": "shell", "args": "whoami"}, "name": "run_whoami"},
#        ]
#        ret = self.runner.run(tasks, "all")
#        print(ret.results_summary)
#        print(ret.results_raw)
#

class TestCommandRunner(unittest.TestCase):
    def setUp(self):
        host_data = [
            {
                "hostname": "testserver",
                "ip": "10.104.9.133",
                "port": 22,
                "username": "root",
                "password": "redhat",
            },
        ]
        inventory = BaseInventory(host_data)
        self.runner = CommandRunner(inventory)

    def test_execute(self):
        res = self.runner.execute('ls', 'all')
        print(res.results_command)
        print(res.results_raw)

class TestPlayBookRunner(unittest.TestCase):
    def setUp(self):
        host_data = [
            {
                "hostname": "testserver",
                "ip": "10.104.9.133",
                "port": 22,
                "username": "root",
                "password": "redhat",
            },
        ]
        
        options = Options(
        listtags=False,
        listtasks=False,
        listhosts=False,
        syntax=False,
        timeout=60,
        connection='ssh',
        module_path='',
        forks=10,
        remote_user='root',
        private_key_file=None,
        ssh_common_args="",
        ssh_extra_args="",
        sftp_extra_args="",
        scp_extra_args="",
        become=None,
        become_method=None,
        become_user=None,
        verbosity=None,
        extra_vars=[],
        check=False,
        playbook_path='/tmp/ping.yml',
        passwords=None,
        diff=False,
        gathering='implicit',
        remote_tmp='/tmp/.ansible'
        ) 
        inventory = BaseInventory(host_data)
        self.runner = PlayBookRunner(inventory, options)
    
    def test_execute(self):
        res = self.runner.run()
        print('*' * 10 )
        print(res['plays'])
        print('*' * 10 )
        print(res['stats'])


if __name__ == "__main__":
    unittest.main()
