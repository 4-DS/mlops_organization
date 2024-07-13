from enum import Enum

class SinaraPlatform(Enum):
    Desktop = 'desktop'
    RemoteVM = 'remote'
    Personal = 'personal'

    def __str__(self):
        return self.value