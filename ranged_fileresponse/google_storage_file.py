import io
import logging
import requests
from google.resumable_media.requests import ChunkedDownload


logger = logging.getLogger(__name__)
MAX_DOWN_SIZE = 0  # 31 * 1024 * 1024

class RangedGoogleStorageFileReader(object):
    """
    Wraps a google storage blob object with an iterator that runs over part (or all) of
    the file defined by start and stop. Blocks of block_size will be returned
    from the starting position, up to, but not including the stop point.
    """

    def __init__(self, media_url, start=0, stop=0, block_size=1024 * 1024, unique_id=None, ranged_response=None):
        """
        Args:
            media_url (str): URL to the resource
            start (int): Where to start reading the file.
            stop (Optional[int]:float): Where to end reading the file.
                Defaults to infinity.
            block_size (Optional[int]): The block_size to read with.
        """
        logger.info(f'Init RangedGoogleStorageFileReader {media_url} {start}:{stop}')
        self.f = io.BytesIO()
        self.media_url = media_url

        # -----------------------------------------------------------------------------------------
        if start < 0:
            # specifica case when we ask for the last N bytes but we still don't know thw file size
            self.download = ChunkedDownload(
                media_url=self.media_url,
                chunk_size=1024,  # just 1K to get the file size,
                stream=io.BytesIO(),
                start=0,
                # headers={},
            )
            chunk = self.download.consume_next_chunk(transport=requests.Session())
            logger.info(f'chunk {chunk} (start<0)')
            size = self.download.total_bytes
            start = size + start  # start is negative
        # -----------------------------------------------------------------------------------------

        self.download = ChunkedDownload(
            media_url=self.media_url,
            chunk_size=block_size,
            stream=self.f,
            start=start,
            # headers={},
        )
        logger.info(f'download {self.download} block {block_size} start {start}')

        # total_bytes is only available after the first chunk is downloaded
        self.initial_chunk = self.download.consume_next_chunk(transport=requests.Session())
        self.size = self.download.total_bytes
        if stop == 0:
            self.stop = self.size
        else:
            self.stop = stop

        self.block_size = block_size
        self.start = start
        self.position = self.start
        self.iter_counter = 0  # just to check

        # ensure a group of chunks with a max size (32 MB limit for http 1)
        if MAX_DOWN_SIZE > 0 and self.size - self.start > MAX_DOWN_SIZE:
            self.stop = self.start + MAX_DOWN_SIZE

        # only if client want something specific, use it, if not, go to the end
        if self.stop > 0:
            self.download.end = self.stop

        self.unique_id = unique_id

        # optionally, a father response to notify chenks sent
        self.ranged_response = ranged_response

    def __len__(self):
        return 1 + (self.size // self.block_size)

    def __iter__(self):
        return self

    def __next__(self):
        """
        Reads the data in chunks.
        """
        self.iter_counter += 1
        self._notify_chunk()
        logger.info(f'ITER {self.iter_counter} {self.position}-{self.block_size}:{self.stop}')
        self.position += self.block_size
        if self.iter_counter == 1:
            return self.initial_chunk.content
        
        if self.download.finished:
            logger.info(f'ITER down finished')
            raise StopIteration() 

        chunk = self.download.consume_next_chunk(transport=requests.Session())
        data = chunk.content
        
        if not data:
            logger.info(f'ITER data finished')
            raise StopIteration()

        return data
        
    def _notify_chunk(self):
        """ notify about a chunk """
        read_to = min(self.block_size, self.stop - self.position)
        my_stop = self.position + read_to
        
        if self.ranged_response:
            kwargs = dict(
                start=self.position,
                stop=my_stop,
                uid=self.unique_id,
                reloaded=False,
                finished=self.download.finished,
                http_range=None
            )
            self.ranged_response.send_signal(**kwargs)
