from backtester.util.position_sizer.position_sizer import PositionSizer


class NoPositionSizer(PositionSizer):
    def __init__(self, config: dict, *args, **kwargs):
        self.constant_position_size = config["constant_position_size"]

    def get_position_size(self, *args, **kwargs):
        return self.constant_position_size

    def on_interval(self, *args, **kwargs):
        pass
