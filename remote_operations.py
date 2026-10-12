"""Bounded remote traversal and non-overwriting moves."""
from pathlib import Path
import posixpath
import fnmatch
from file_tools import validate_remote_name


def safe_remote_name(name):
    if not name or name in (".", "..") or "/" in name or "\\" in name or any(ord(c)<32 for c in name):
        raise ValueError("Unsafe remote entry name")
    return name


def walk_remote(client, root, recursive, checkpoint, progress=None):
    if recursive and hasattr(client, "check_directory_traversal"): client.check_directory_traversal(root)
    pending=[(posixpath.normpath(root),0)]; visited=set()
    while pending:
        checkpoint()
        folder,depth=pending.pop()
        if folder in visited: continue
        if depth>64 or len(visited)>=10000: raise ValueError('Remote traversal limit reached')
        visited.add(folder)
        entries=(getattr(client, "listdir_safe", client.listdir) if recursive else client.listdir)(folder)
        if progress: progress(len(visited))
        for name,directory,size in entries:
            checkpoint()
            safe_remote_name(name)
            path=posixpath.join(folder,name)
            yield name,directory,size,path
            if recursive and directory: pending.append((path,depth+1))


def search_remote(client,root,pattern,recursive,checkpoint,progress=None):
    matches=[]
    for name,directory,size,path in walk_remote(client,root,recursive,checkpoint,progress):
        if fnmatch.fnmatchcase(name.casefold(),pattern.casefold()):
            if len(matches)>=10000: raise ValueError('Search result limit reached; narrow your search')
            matches.append((name,directory,size,path))
    return matches


def plan_downloads(client,entries,target,file_filter,checkpoint):
    target=Path(target).resolve(); directories=[]; files=[]; destinations=set()
    def destination(relative):
        result=target.joinpath(*relative).resolve()
        if not result.is_relative_to(target): raise ValueError('Download destination escapes local folder')
        key=str(result).casefold()
        if key in destinations: raise ValueError('Remote names collide on Windows')
        destinations.add(key)
        return result
    for source,directory in entries:
        checkpoint(); name=validate_remote_name(posixpath.basename(source.rstrip('/')))
        if not file_filter.allows(name,directory=directory):continue
        base=destination([name])
        if directory:
            if hasattr(client, "check_directory_traversal"): client.check_directory_traversal(source)
            directories.append(str(base)); pending=[(source,base,0)]; visited=set()
            while pending:
                checkpoint(); remote,local,depth=pending.pop()
                if remote in visited:continue
                if depth>64 or len(visited)>=10000:raise ValueError('Remote traversal limit reached')
                visited.add(remote)
                for child,isdir,size in getattr(client, "listdir_safe", client.listdir)(remote):
                    checkpoint();validate_remote_name(child)
                    if not file_filter.allows(child,directory=isdir):continue
                    child_remote=posixpath.join(remote,child)
                    child_local=destination([*local.relative_to(target).parts,child])
                    if isdir:
                        directories.append(str(child_local));pending.append((child_remote,child_local,depth+1))
                    else:
                        if len(files)>=100000:raise ValueError("Download plan limit reached")
                        files.append((child_remote,str(child_local)))
        else:files.append((source,str(base)))
    return directories,files


def move_remote(client,entries,target,checkpoint):
    target=posixpath.normpath(target)
    existing={name.casefold() for name,_,_ in client.listdir(target)}
    planned=[]
    normalized=[(posixpath.normpath(source), directory) for source,directory in entries]
    if any(directory and other.startswith(source.rstrip("/")+"/") for source,directory in normalized for other,_ in normalized if other!=source):
        raise ValueError("Select either a folder or its children, not both")
    for source,directory in normalized:
        checkpoint();source=posixpath.normpath(source)
        name=validate_remote_name(posixpath.basename(source))
        dest=posixpath.join(target,name)
        if source==dest:raise ValueError('Source and destination are the same')
        if directory and (target==source or target.startswith(source.rstrip('/')+'/')):
            raise ValueError('Cannot move a folder into itself')
        if name.casefold() in existing:raise FileExistsError('Destination already contains '+name)
        existing.add(name.casefold());planned.append((source,dest))
    for source,dest in planned:
        checkpoint();client.rename(source,dest)
    return planned

def delete_remote(client,entries,checkpoint):
    """Plan first, then delete files and deepest folders; no rollback."""
    files=[];folders=[]
    for source,directory in entries:
        source=posixpath.normpath(source)
        if source in ('/','.','..'):raise ValueError('Cannot delete a remote root')
        validate_remote_name(posixpath.basename(source))
        checkpoint()
        if directory:
            folders.append(source)
            for name,isdir,size,path in walk_remote(client,source,True,checkpoint):
                (folders if isdir else files).append(path)
        else:files.append(source)
    for path in dict.fromkeys(files):
        checkpoint();client.remove_file(path)
    for path in sorted(set(folders),key=lambda p:p.count('/'),reverse=True):
        checkpoint();client.remove_directory(path)
    return len(set(files)),len(set(folders))
