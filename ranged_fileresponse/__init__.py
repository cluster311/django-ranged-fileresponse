import os
from django.http.response import FileResponse
# send signals to know about sended chunks
import django.dispatch


class RangedFileReader(object):
    """
    Wraps a file like object with an iterator that runs over part (or all) of
    the file defined by start and stop. Blocks of block_size will be returned
    from the starting position, up to, but not including the stop point.
    """
    block_size = 1024 * 1024  # raises too many signals: 8192

    def __init__(self, file_like, start=0, stop=float('inf'), block_size=None, unique_id=None):
        """
        Args:
            file_like (File): A file-like object.
            start (int): Where to start reading the file.
            stop (Optional[int]:float): Where to end reading the file.
                Defaults to infinity.
            block_size (Optional[int]): The block_size to read with.
        """
        self.f = file_like
        # self.size = len(self.f.read())
        self.size = os.fstat(self.f.fileno()).st_size

        self.block_size = block_size or RangedFileReader.block_size
        self.start = start
        self.stop = stop
        self.unique_id = unique_id

    def __iter__(self):
        """
        Reads the data in chunks.
        """
        self.f.seek(self.start)
        position = self.start
        while position < self.stop:
            read_to = min(self.block_size, self.stop - position)
            data = self.f.read(read_to)
            my_stop = position + read_to
            # notify about this chunk
            finished = not data or (position + self.block_size >= self.stop)
            # we process this many times because the clients ask for start point and not the finsh ones
            # so we get chuck from 0 to end, then from N to end, then NN to end, etc.
            ranged_file_response_signal.send(sender=RangedFileResponse,
                                             start=position,
                                             stop=my_stop,
                                             uid=self.unique_id,
                                             reloaded=False,
                                             finished=finished,
                                             http_range=None)
            if not data:
                break
            yield data
            position += self.block_size

    def parse_range_header(self, header, resource_size):
        """
        Parses a range header into a list of two-tuples (start, stop) where
        `start` is the starting byte of the range (inclusive) and
        `stop` is the ending byte position of the range (exclusive).

        Args:
            header (str): The HTTP_RANGE request header.
            resource_size (int): The size of the file in bytes.

        Returns:
            None if the value of the header is not syntatically valid.
        """
        if not header or '=' not in header:
            return None

        ranges = []
        units, range_ = header.split('=', 1)
        units = units.strip().lower()

        if units != 'bytes':
            return None

        for val in range_.split(','):
            val = val.strip()
            if '-' not in val:
                return None

            if val.startswith('-'):
                # suffix-byte-range-spec: this form specifies the last N bytes
                # of an entity-body.
                start = resource_size + int(val)
                if start < 0:
                    start = 0
                stop = resource_size
            else:
                # byte-range-spec: first-byte-pos "-" [last-byte-pos].
                start, stop = val.split('-', 1)
                start = int(start)
                # The +1 is here since we want the stopping point to be
                # exclusive, whereas in the HTTP spec, the last-byte-pos
                # is inclusive.
                stop = int(stop) + 1 if stop else resource_size
                if start >= stop:
                    return None

            ranges.append((start, stop))

        return ranges


class RangedFileResponse(FileResponse):
    """
    This is a modified FileResponse that returns `Content-Range` headers with
    the response, so browsers that request the file, can stream the response
    properly.
    """

    def __init__(self, request, file,
                 block_size=None,  # allow to change
                 unique_id=None,  # to follow chunks outside via signal
                 *args, **kwargs):
        """
        RangedFileResponse constructor also requires a request, which
        checks whether range headers should be added to the response.

        Args:
            request(WGSIRequest): The Django request object.
            file (File): A file-like object.
        """
        self.unique_id = unique_id
        self.ranged_file = RangedFileReader(file, block_size=block_size, unique_id=self.unique_id)
        super(RangedFileResponse, self).__init__(self.ranged_file, *args, **kwargs)
        if hasattr(file, 'close') and hasattr(self, '_closable_objects'):
            self._closable_objects.append(file)

        # default if we dont have range readed
        self.last_start = -1
        self.last_stop = -1
        
        if 'HTTP_RANGE' in request.META:
            self.add_range_headers(request.META['HTTP_RANGE'])

        start = self.last_start
        stop = self.last_stop
        # notify about this chunk
        ranged_file_response_signal.send(sender=self.__class__,
                                         start=start,
                                         stop=stop,
                                         uid=self.unique_id,
                                         reloaded=True,  # the user (or navigator) asks for another part
                                         finished=False,
                                         http_range=request.META.get('HTTP_RANGE', None)
                                         )

    def add_range_headers(self, range_header):
        """
        Adds several headers that are necessary for a streaming file
        response, in order for Safari to play audio files. Also
        sets the HTTP status_code to 206 (partial content).

        Args:
            range_header (str): Browser HTTP_RANGE request header.
        """
        self['Accept-Ranges'] = 'bytes'
        size = self.ranged_file.size

        try:
            ranges = self.ranged_file.parse_range_header(range_header, size)
        except ValueError:
            ranges = None
        # Only handle syntactically valid headers, that are simple (no
        # multipart byteranges).
        if ranges is not None and len(ranges) == 1:
            start, stop = ranges[0]
            self.last_start = start
            self.last_stop = stop
            if start >= size:
                # Requested range not satisfiable.
                self.status_code = 416
                return

            if stop >= size:
                stop = size
            self.last_stop = stop

            self.ranged_file.start = start
            self.ranged_file.stop = stop
            self['Content-Range'] = 'bytes %d-%d/%d' % (start, stop - 1, size)
            self['Content-Length'] = stop - start
            self.status_code = 206


args = ['start',  # first byte
        'stop',  # last byte
        'uid',  # analytics unique id
        'reloaded',  # the user (or navigator) ask for diffrent data
        'finished',  # finished streaming
        'http_range' # what we asked for 
        ]
ranged_file_response_signal = django.dispatch.Signal(providing_args=args)