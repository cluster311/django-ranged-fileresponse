# django-ranged-fileresponse

Django do not include a HTTP Ranged Response. There is a [Django ticket](https://code.djangoproject.com/ticket/22479)
for this, however no indication that this feature will be implemented soon.

The [original suggested fix](https://github.com/satchamo/django/commit/2ce75c5c4bee2a858c0214d136bfcd351fcde11d)
applies the code to Django's static view. This is a packaged version of that fix,
but uses a modified FileResponse, instead of applying it to Django's static view.

Forked originally from a project that only handles local files
This fork also include Ranged Responses from open Google Storage Blobs

## Status

~Maintained

## Usage

### Requirements

 * django >= 3.2

### Installation

    pip install -e git://github.com/cluster311/django-ranged-fileresponse#egg=django-ranged-fileresponse==0.1.8

### Running

#### Local files

```python
    from ranged_fileresponse.local import RangedLocalFileResponse

    def some_proxy_view(request):
        filename = 'myfile.wav'
        response = RangedLocalFileResponse(request, open(filename, 'r'), content_type='audio/wav')
        response['Content-Disposition'] = 'attachment; filename="%s"' % filename
        return response
```

#### Google Storage files

```python
    from ranged_fileresponse.google import RangedGoogleBlobResponse

    def some_proxy_view(request):
        filename = 'myfile.wav'
        response = RangedGoogleBlobResponse(
            request,
            "https://storage.googleapis.com/parlarispa-app-files/audios/s02e38-adria-mercader.mp3",  # the media URL
            content_type='audio/wav'
        )
        response['Content-Disposition'] = 'attachment; filename="%s"' % filename
        return response
```

### Signals

```python
from django.dispatch import receiver
from ranged_fileresponse import ranged_file_response_signal

@receiver(ranged_file_response_signal)
def chunk_received(sender, uid, start, reloaded, finished, **kwargs):
    # do something with this data
    # save_stats(uid=uid, start=start, reloaded=reloaded, finished=finished)
```

## Contributing

See the [CONTRIBUTING.md](CONTRIBUTING.md) file on how to contribute to this project.

## Contributors

See the [CONTRIBUTORS.md](CONTRIBUTORS.md) file for a list of contributors to the project.

## Roadmap

### Changelog

The changelog can be found in the [CHANGELOG.md](CHANGELOG.md) file.

### In progress

 * Maintaining

## Get in touch with a developer

If you want to report an issue see the [CONTRIBUTING.md](CONTRIBUTING.md) file for more info.

We will be happy to answer your other questions at opensource@wearespindle.com

## License

django-ranged-fileresponse is made available under the MIT license. See the [LICENSE file](LICENSE) for more info.
