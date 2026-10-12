import threading
from unittest.mock import Mock
import pytest
from remote_operations import search_remote, plan_downloads, move_remote, delete_remote
from transfer_control import OperationCancelled, check_cancelled
from file_filters import FileFilter


class TreeClient:
    def __init__(self):
        self.tree={'/files':[('project',True,0),('top.txt',False,2)],
                   '/files/project':[('sub',True,0),('empty',True,0),('a.txt',False,4)],
                   '/files/project/sub':[('b.txt',False,5)], '/files/project/empty':[], '/target':[]}
        self.rename=Mock();self.remove_file=Mock();self.remove_directory=Mock()
    def listdir(self,path):return self.tree[path]


def test_search_recursive_glob_and_cancel():
    client=TreeClient();scanned=[]
    assert [r[3] for r in search_remote(client,'/files','*.TXT',False,lambda:None)]==['/files/top.txt']
    assert {r[3] for r in search_remote(client,'/files','*.TXT',True,lambda:None,scanned.append)}=={'/files/top.txt','/files/project/a.txt','/files/project/sub/b.txt'}
    assert scanned[-1]==4
    cancelled=threading.Event();cancelled.set()
    with pytest.raises(OperationCancelled):search_remote(client,'/files','*',True,lambda:check_cancelled(cancelled))


def test_recursive_download_preserves_empty_folders_and_prunes(tmp_path):
    client=TreeClient()
    dirs,files=plan_downloads(client,[('/files/project',True)],tmp_path,FileFilter(),lambda:None)
    assert str(tmp_path/'project'/'empty') in dirs
    assert ('/files/project/sub/b.txt',str(tmp_path/'project'/'sub'/'b.txt')) in files
    dirs,files=plan_downloads(client,[('/files/project',True)],tmp_path,FileFilter(exclude='sub'),lambda:None)
    assert not any('/sub/' in source for source,_ in files)


@pytest.mark.parametrize('name',['../escape','CON','a:b','bad\\name'])
def test_download_rejects_unsafe_windows_names(tmp_path,name):
    client=TreeClient();client.tree['/files/project']=[(name,False,3)]
    with pytest.raises(ValueError):plan_downloads(client,[('/files/project',True)],tmp_path,FileFilter(),lambda:None)


def test_download_rejects_windows_collisions_and_junction_escape(tmp_path):
    client=TreeClient();client.tree['/files/project']=[('A.txt',False,3),('a.txt',False,3)]
    with pytest.raises(ValueError,match='collide'):plan_downloads(client,[('/files/project',True)],tmp_path,FileFilter(),lambda:None)


def test_moves_preflight_all_conflicts_before_rename():
    client=TreeClient();client.tree['/target']=[('top.txt',False,1)]
    with pytest.raises(FileExistsError):move_remote(client,[('/files/project',True),('/files/top.txt',False)],'/target',lambda:None)
    client.rename.assert_not_called()
    with pytest.raises(ValueError,match='itself'):move_remote(client,[('/files/project',True)],'/files/project/sub',lambda:None)
    client.rename.assert_not_called()
    move_remote(client,[('/files/project',True)],'/target',lambda:None)
    client.rename.assert_called_once_with('/files/project','/target/project')


def test_delete_plans_before_mutation_and_removes_children_first():
    client=TreeClient();order=[]
    client.remove_file.side_effect=lambda p:order.append(('file',p))
    client.remove_directory.side_effect=lambda p:order.append(('dir',p))
    assert delete_remote(client,[('/files/project',True)],lambda:None)==(2,3)
    assert order[-1]==('dir','/files/project')
    assert all(kind=='file' for kind,_ in order[:2])
    with pytest.raises(ValueError):delete_remote(client,[('/',True)],lambda:None)


def test_server_failure_does_not_suppress_delete_error():
    client=TreeClient();client.remove_file.side_effect=PermissionError('550 denied')
    with pytest.raises(PermissionError):delete_remote(client,[('/files/project',True)],lambda:None)
    client.remove_directory.assert_not_called()


def test_recursive_ftp_requires_mlsd_and_adapter_commands():
    import ftplib
    from transfer_client import Client
    client=Client();client.kind='FTPES';client.conn=Mock();client.conn.mlsd.side_effect=ftplib.error_perm('500 unavailable')
    with pytest.raises(RuntimeError,match='MLSD'):client.listdir_safe('/files')
    client.conn.cwd.assert_not_called()
    client.remove_file('/files/a');client.remove_directory('/files/b');client.rename('/files/a','/target/a')
    client.conn.delete.assert_called_once_with('/files/a');client.conn.rmdir.assert_called_once_with('/files/b')
    client.conn.rename.assert_called_once_with('/files/a','/target/a')

def test_selected_directory_link_is_rejected_before_recursive_mutation():
    import stat
    from types import SimpleNamespace
    from transfer_client import Client
    client=Client();client.kind='SFTP';client.conn=Mock()
    client.conn.lstat.return_value=SimpleNamespace(st_mode=stat.S_IFLNK)
    with pytest.raises(ValueError,match='links'):delete_remote(client,[('/link/',True)],lambda:None)
    client.conn.lstat.assert_called_once_with('/link')
    client.conn.remove.assert_not_called();client.conn.rmdir.assert_not_called()


def test_parent_child_move_selection_rejected_before_any_rename():
    client=TreeClient()
    with pytest.raises(ValueError,match='children'):move_remote(client,[('/files/project',True),('/files/project/a.txt',False)],'/target',lambda:None)
    client.rename.assert_not_called()
