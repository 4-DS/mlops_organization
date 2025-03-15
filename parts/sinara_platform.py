from enum import Enum

class SinaraPlatform(Enum):
    #Desktop = 'desktop'
    #RemoteVM = 'remote'
    #Personal = 'personal'
    PersonalPublicDesktop = "personal_public_desktop"

    def __str__(self):
        return self.value