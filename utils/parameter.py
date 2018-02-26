import os
import shutil
from datetime import datetime

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from tensorflow.contrib.training import HParams

from utils.helper import touch_dir
from utils.logger import get_logger


def add_param_recur(root, p_tree):
    for k, v in p_tree:
        if isinstance(v, CommentedMap):
            new_node = HParams()
            add_param_recur(new_node, v.items())
            root.add_hparam(k, new_node)
        else:
            root.add_hparam(k, v)


class YParams(HParams):
    def __init__(self, yaml_fn, config_name):
        super().__init__()
        with open(yaml_fn) as fp:
            add_param_recur(self, YAML().load(fp)[config_name].items())
        self.yaml_fn = yaml_fn

    def copyto(self, dir):
        shutil.copy2(self.yaml_fn, dir)


class ModelParams(YParams):
    pass


class AppConfig(YParams):
    def __init__(self, yaml_fn, config_name, app_name=None):
        super().__init__(yaml_fn, config_name)
        self.data_dir = self.work_dir + self.data_dir
        self.log_dir = self.work_dir + self.log_dir
        self.script_dir = self.work_dir + self.script_dir
        self.output_dir = self.work_dir + self.output_dir
        self.instance_name = os.getenv('APPNAME', 'app') + datetime.now().strftime(
            "%m%d-%H%M") if not app_name else app_name
        self.log_path = self.log_dir + self.instance_name + '.log'
        self.output_path = self.output_dir + self.instance_name
        self.model_dir = self.model_dir + self.instance_name + '/'
        self.dataio_path = self.model_dir + 'dataio.yaml'
        touch_dir(self.output_dir)
        touch_dir(self.model_dir)
        import shared
        shared.logger = get_logger(__name__, self.log_path, self.log_format)
