from django.dispatch import Signal


class RangedResponse:

    def send_signal(self, **kwargs):
        ranged_file_response_signal.send(
            sender=self.__class__,
            **kwargs
        )


ranged_file_response_signal = Signal(
    providing_args=[
        'start',  # first byte
        'stop',  # last byte
        'uid',  # analytics unique id
        'reloaded',  # the user (or navigator) ask for diffrent data
        'finished',  # finished streaming
        'http_range' # what we asked for 
        ]
)
