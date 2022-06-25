from setuptools import setup

tests_require = [
    'pytest>=3.0.5',
    'pytest-cov>=2.4.0',
    'pytest-flake8>=0.8.1',
    'django>=1.8.0',
]

required = [
    'django_storages==1.12.3'
]

setup(
    name='django-ranged-fileresponse',
    version='0.1.9',
    description='Modified Django FileResponse that adds Content-Range headers.',
    # url='https://github.com/wearespindle/django-ranged-fileresponse',
    url='https://github.com/cluster311/django-ranged-fileresponse',
    author='Cluster 311 (forked from Spindle work)',
    author_email='cluster311@gmail.com',
    license='MIT',
    packages=['ranged_fileresponse'],
    zip_safe=False,
    install_requires=required,
    tests_require=tests_require,
    extras_require={
        'test': tests_require,
    },
)
