"""Case-insensitive filename/relative-path glob rules for browsing and uploads."""
from fnmatch import fnmatchcase


def patterns(text):
    return tuple(part.strip().replace('\\', '/').casefold()
                 for part in text.split(';') if part.strip())


class FileFilter:
    def __init__(self, include='*', exclude=''):
        self.include = patterns(include) or ('*',)
        self.exclude = patterns(exclude)

    def allows(self, name, relative=None, directory=False):
        candidates = {name.casefold(), (relative or name).replace('\\', '/').casefold()}
        def matches(rules):
            return any(fnmatchcase(value, rule) for value in candidates for rule in rules)
        return not matches(self.exclude) and (directory or matches(self.include))
