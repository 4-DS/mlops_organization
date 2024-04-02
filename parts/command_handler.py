from .server import SinaraServer
from .model import SinaraModel

class CommandHandler:

    @staticmethod
    def add_command_handlers(root_parser, subject_parser):
        print('This is ml_ops_organization')
        SinaraServer.add_command_handlers(root_parser, subject_parser)
        SinaraModel.add_command_handlers(root_parser, subject_parser)