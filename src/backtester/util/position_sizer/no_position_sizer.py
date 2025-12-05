from backtester.util.position_sizer.position_sizer import PositionSizer


class NoPositionSizer(PositionSizer):
    def __init__(self, config: dict, *args, **kwargs):
        self.initial_position_size = config["initial_position_size"]

    def get_position_size(self, *args, **kwargs):
        return self.initial_position_size
