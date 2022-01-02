from django.core.exceptions import BadRequest
from django.http.response import FileResponse

from ranged_fileresponse import RangedResponse
from ranged_fileresponse.google_storage_file import RangedGoogleStorageFileReader


class RangedGoogleBlobResponse(FileResponse, RangedResponse):
    """
    This is a modified FileResponse that returns `Content-Range` headers with
    the response, so browsers that request a media URL from Google,
    can stream the response properly.
    """

    def __init__(self, request, media_url,
                 block_size=None,  # allow to change
                 unique_id=None,  # to follow chunks outside via signal
                 *args, **kwargs):
        """
        Constructor also requires a request, which
        checks whether range headers should be added to the response.

        Args:
            request(WGSIRequest): The Django request object.
            file (File): A file-like object.
        """
        self.unique_id = unique_id

        if 'HTTP_RANGE' in request.META:
            # we need the size to define exactly the ranges but we don't have them
            # until we read the first chunk
            start, stop = self.get_base_ranges(request.META['HTTP_RANGE'])
        else:
            start = 0
            stop = 0

        self.ranged_file = RangedGoogleStorageFileReader(
            media_url,
            block_size=block_size,
            start=start,
            stop=stop,
            unique_id=self.unique_id,
            ranged_response=self,  # connected to allow child to send signals
        )
        size = self.ranged_file.size
        super().__init__(self.ranged_file, *args, **kwargs)

        final_start = self.ranged_file.start
        final_stop = self.ranged_file.stop

        # fix ranges using the file size and add them to the response
        if 'HTTP_RANGE' in request.META:
            self.add_range_headers(final_start, final_stop, size)

        signal_kwargs = dict(
            start=start,
            stop=stop,
            uid=self.unique_id,
            reloaded=True,  # the user (or navigator) asks for another part
            finished=False,
            http_range=request.META.get('HTTP_RANGE', None)
        )
        self.send_signal(**signal_kwargs)

    def get_base_ranges(self, header):
        """
        Parses a range header into a list of two-tuples (start, stop) where
        `start` is the starting byte of the range (inclusive) and
        `stop` is the ending byte position of the range (exclusive).

        Args:
            header (str): The HTTP_RANGE request header.

        Returns:
            (start, stop) tuple or (None, None) if the value of the header is not syntatically valid.
        
        Specs https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Range
        Syntax
            Range: <unit>=<range-start>-
            Range: <unit>=<range-start>-<range-end>
            Range: <unit>=<range-start>-<range-end>, <range-start>-<range-end>
            Range: <unit>=<range-start>-<range-end>, <range-start>-<range-end>, <range-start>-<range-end>
            Range: <unit>=-<suffix-length>

        Directives
            <unit>
            The unit in which ranges are specified. This is usually bytes.

            <range-start>
            An integer in the given unit indicating the beginning of the request range.

            <range-end>
            An integer in the given unit indicating the end of the requested range. This value is optional and, if omitted, the end of the document is taken as the end of the range.

            <suffix-length>
            An integer in the given unit indicating the number of units at the end of the file to return.
        """

        if not header or '=' not in header:
            return None, None

        start = None
        stop = None
        units, range_ = header.split('=', 1)
        units = units.strip().lower()

        if units != 'bytes':
            raise BadRequest('Only bytes ranges are supported')

        # We don't handle multipart byteranges, just the first one
        val = range_.split(',')[0].strip()
        if '-' not in val:
            raise BadRequest(f'HTTP_RANGE header is bad defined (missing "-"): {header}')
        
        start, stop = val.split('-', 1)
        if start != '' and not start.isnumeric():
            raise BadRequest(f'HTTP_RANGE header is bad defined (start is not numeric): {header}')
        if stop != '' and not stop.isnumeric():
            raise BadRequest(f'HTTP_RANGE header is bad defined (stop is not numeric): {header}')

        stop = 0 if stop == '' else int(stop)
        if start == '' and stop > 0:  # corner case
            # start must be (FILE_SIZE - stop) but we don't know the file size
            # stop must be -> FILE_SIZE but we don't know the file size
            # Define start as negative as a flag
            start = -int(stop)
            stop = 0
        else:
            start = 0 if start == '' else int(start)

        return start, stop

    def add_range_headers(self, start, stop, size):
        """
        Adds several headers that are necessary for a streaming file
        response, in order for Safari to play audio files. Also
        sets the HTTP status_code to 206 (partial content).

        Args:
            range_header (str): Browser HTTP_RANGE request header.
        """
        self['Accept-Ranges'] = 'bytes'

        if start >= size:
            # Requested range not satisfiable.
            self.status_code = 416
            return

        if stop >= size:
            stop = size

        self['Content-Range'] = 'bytes %d-%d/%d' % (start, stop - 1, size)
        self['Content-Length'] = stop - start
        self.status_code = 206
