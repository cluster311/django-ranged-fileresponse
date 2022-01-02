from io import BufferedReader, BytesIO
import os
from django.http.response import FileResponse
from ranged_fileresponse import RangedResponse


class RangedFileReader(object):
    """
    Wraps a file like object with an iterator that runs over part (or all) of
    the file defined by start and stop. Blocks of block_size will be returned
    from the starting position, up to, but not including the stop point.
    """

    def __init__(self, file_like, start=0, stop=-1, block_size=1024 * 1024, unique_id=None, ranged_response=None):
        """
        Args:
            file_like (File): A file-like object.
            start (int): Where to start reading the file.
            stop (Optional[int]:float): Where to end reading the file.
                Defaults to infinity.
            block_size (Optional[int]): The block_size to read with.
        """
        self.f = file_like
        
        if type(self.f) == BufferedReader:  # a file from filesystem
            self.size = os.fstat(self.f.fileno()).st_size
        elif type(self.f) == BytesIO:  # a file like
            self.size = self.f.getbuffer().nbytes
        else:
            raise Exception('Unexpected buffer to stream ranged')

        self.block_size = block_size
        self.start = start
        self.unique_id = unique_id
        
        # the client frecuently do not ask for the stop bytes so we always send all the file
        # the client not uses all of this.
        # I try to force client to ask again
        if stop == -1:
            stop = min(start + stop, self.size)
        
        self.stop = stop
        self.ranged_response = ranged_response
        
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
            if self.ranged_response:
                # notify about this chunk
                finished = position + self.block_size >= self.size  # size is real, stop is my idea to break in parts
                # we process this many times because the clients ask for start point and not the finsh ones
                # so we get chuck from 0 to end, then from N to end, then NN to end, etc.
                
                self.ranged_response.send_signal(
                    start=position,
                    stop=my_stop,
                    uid=self.unique_id,
                    reloaded=False,
                    finished=finished,
                    http_range=None
                )
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


class RangedLocalFileResponse(FileResponse, RangedResponse):
    """
    This is a modified FileResponse that returns `Content-Range` headers with
    the response, so browsers that request the file, can stream the response
    properly.
    """

    def __init__(self, request, file,
                 block_size=None,  # allow to change
                 unique_id=None,  # to follow chunks outside via signal
                 max_content_size=0,  # not send all file, send parts so the client need to ask for more and I can do analytics
                 *args, **kwargs):
        """
        Constructor also requires a request, which
        checks whether range headers should be added to the response.

        Args:
            request(WGSIRequest): The Django request object.
            file (File): A file-like object.
        """
        self.unique_id = unique_id
        if max_content_size == 0:
            max_content_size = float('inf')
        
        self.ranged_file = RangedFileReader(file,
                                            block_size=block_size,
                                            stop=max_content_size,
                                            unique_id=self.unique_id)
        super().__init__(self.ranged_file, *args, **kwargs)
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
        self.send_signal(
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
