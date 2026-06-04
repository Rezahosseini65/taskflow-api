from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'taskflow.accounts'

    def ready(self):

        import taskflow.accounts.authentication
