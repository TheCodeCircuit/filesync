import json
import os

from models import ClientConfig, UserConfig, ServerIdentity


class ConfigManager:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = self._default_config()

    def load(self):
        if not os.path.exists(self.config_path):
            self.config = self._default_config()
            self.save()
            return self.config

        with open(self.config_path, "r") as f:
            data = json.load(f)

        self.config = self._from_dict(data)

        return self.config

    def save(self):
        data = self._to_dict(self.config)

        with open(self.config_path, "w") as f:
            json.dump(data, f, indent=4)

    def get_config(self):
        return self.config

    def update_user_config(self, user_config):
        self.config.user = user_config
        self.save()

    def update_identity(self, identity):
        self.config.identity = identity
        self.save()

    def reset_identity(self):
        self.config.identity = ServerIdentity(
            device_id=None,
            sync_space_id=None,
            access_token=None,
            refresh_token=None
        )

        self.save()

    def _default_config(self):
        user_config = UserConfig(
            sync_folder=None,
            server_url=None
        )

        server_identity = ServerIdentity(
            device_id=None,
            sync_space_id=None,
            access_token=None,
            refresh_token=None
        )

        config = ClientConfig(
            user=user_config,
            identity=server_identity
        )

        return config

    def _to_dict(self, client_config):
        user_dictionary = {
            "sync_folder": client_config.user.sync_folder,
            "server_url": client_config.user.server_url
        }

        identity_dictionary = {
            "device_id": client_config.identity.device_id,
            "sync_space_id": client_config.identity.sync_space_id,
            "access_token": client_config.identity.access_token,
            "refresh_token": client_config.identity.refresh_token
        }

        config_dictionary = {
            "user": user_dictionary,
            "identity": identity_dictionary
        }

        return config_dictionary

    def _from_dict(self, config_dict):
        user_dict = config_dict["user"]

        user = UserConfig(
            sync_folder=user_dict["sync_folder"],
            server_url=user_dict["server_url"]
        )

        identity_dict = config_dict["identity"]

        identity = ServerIdentity(
            device_id=identity_dict["device_id"],
            sync_space_id=identity_dict["sync_space_id"],
            access_token=identity_dict["access_token"],
            refresh_token=identity_dict["refresh_token"]
        )

        client_config = ClientConfig(
            user=user,
            identity=identity
        )

        return client_config