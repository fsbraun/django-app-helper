#!/usr/bin/env python
from __future__ import print_function, with_statement
import contextlib
import pkgutil
import pyclbr
import subprocess
import os
import sys
import warnings

from docopt import docopt
from django.utils.encoding import force_text
from django.utils.importlib import import_module


from .utils import work_in, DJANGO_1_6, DJANGO_1_5, temp_dir, _make_settings

__doc__ = '''django CMS applications development helper script.

To use a different database, set the DATABASE_URL environment variable to a
dj-database-url compatible value.

Usage:
    djangocms-helper <application> test [--failfast] [--migrate] [<test-label>...] [--xvfb] [--runner=<test.runner.class>] [--extra-settings=</path/to/settings.py>] [--cms]
    djangocms-helper <application> shell [--extra-settings=</path/to/settings.py>] [--cms]
    djangocms-helper <application> compilemessages [--extra-settings=</path/to/settings.py>] [--cms]
    djangocms-helper <application> makemessages [--extra-settings=</path/to/settings.py>] [--cms]
    djangocms-helper <application> makemigrations [--extra-settings=</path/to/settings.py>] [--cms]
    djangocms-helper <application> pyflakes [--extra-settings=</path/to/settings.py>] [--cms]
    djangocms-helper <application> authors [--extra-settings=</path/to/settings.py>] [--cms]

Options:
    -h --help                   Show this screen.
    --version                   Show version.
    --migrate                   Use south migrations in test.
    --cms                       Add support for CMS in the project configuration.
    --failfast                  Stop tests on first failure.
    --xvfb                      Use a virtual X framebuffer for frontend testing, requires xvfbwrapper to be installed.
    --extra-settings            Filesystem path to a custom cms_helper file which defines custom settings
    --runner                    Dotted path to a custom test runner
'''


def _get_test_labels(application):
    test_labels = []
    for module in [name for _, name, _ in pkgutil.iter_modules([os.path.join(application, "tests")])]:
        clsmembers = pyclbr.readmodule("%s.tests.%s" % (application, module))
        for clsname, cls in clsmembers.items():
            for method, _ in cls.methods.items():
                if method.startswith('test_'):
                    test_labels.append('%s.%s.%s' % (application, clsname, method))
    test_labels = sorted(test_labels)
    return test_labels


def _test_run_worker(test_labels, failfast=False,
                     test_runner='django.test.simple.DjangoTestSuiteRunner'):
    warnings.filterwarnings(
        'error', r"DateTimeField received a naive datetime",
        RuntimeWarning, r'django\.db\.models\.fields')
    from django.conf import settings
    from django.test.utils import get_runner

    settings.TEST_RUNNER = test_runner
    TestRunner = get_runner(settings)

    test_runner = TestRunner(verbosity=1, interactive=False, failfast=failfast)
    failures = test_runner.run_tests(test_labels)
    return failures


def test(test_labels, application, failfast=False,
         test_runner='django.test.simple.DjangoTestSuiteRunner'):
    """
    Runs the test suite
    :param test_labels: space separated list of test labels
    :param failfast: option to stop the testsuite on the first error
    """
    test_labels = test_labels or _get_test_labels(application)
    return _test_run_worker(test_labels, failfast, test_runner)


def compilemessages(application):
    """
    Compiles locale messages
    """
    from django.core.management import call_command

    with work_in(application):
        call_command('compilemessages', all=True)


def makemessages(application):
    """
    Updates the locale message files
    """
    from django.core.management import call_command

    with work_in(application):
        if DJANGO_1_5:
            call_command('makemessages', locale='en')
        else:
            call_command('makemessages', locale=('en',))


def shell():
    """
    Returns a django shell for the test project
    """
    from django.core.management import call_command

    call_command('shell')


def makemigrations(application):
    """
    Generate migrations (for both south and django 1.7+)
    """
    from django.core.management import call_command
    from .utils import load_from_file

    if DJANGO_1_6:
        try:
            loaded = load_from_file(os.path.join(application, 'migrations',
                                                 '0001_initial.py'))
        except IOError:
            loaded = None
        initial = loaded is None
        call_command('schemamigration',
                     initial=initial,
                     auto=(not initial),
                     *(application,))
    else:
        call_command('makemigrations', *(application,))


def generate_authors():
    """
    Updates the authors list
    """
    print("Generating AUTHORS")

    # Get our list of authors
    print("Collecting author names")
    r = subprocess.Popen(["git", "log", "--use-mailmap", "--format=%aN"],
                         stdout=subprocess.PIPE)
    seen_authors = []
    authors = []
    with open('AUTHORS', 'r') as f:
        for line in f.readlines():
            if line.startswith("*"):
                author = force_text(line).strip("* \n")
                if author.lower() not in seen_authors:
                    seen_authors.append(author.lower())
                    authors.append(author)
    for author in r.stdout.readlines():
        author = force_text(author).strip()
        if author.lower() not in seen_authors:
            seen_authors.append(author.lower())
            authors.append(author)

    # Sort our list of Authors by their case insensitive name
    authors = sorted(authors, key=lambda x: x.lower())

    # Write our authors to the AUTHORS file
    print(u"Authors (%s):\n\n\n* %s" % (len(authors), u"\n* ".join(authors)))


def static_analisys(application):
    """
    Performs a pyflakes static analysis with the same configuration as
    django CMS testsuite
    """
    try:
        from cms.test_utils.util.static_analysis import pyflakes
        application_module = import_module(application)
        assert pyflakes((application_module,)) == 0
    except ImportError:
        print(u"Static analisys available only if django CMS is installed")


def core(args, application):
    from django.conf import settings

    # configure django
    warnings.filterwarnings(
        'error', r"DateTimeField received a naive datetime",
        RuntimeWarning, r'django\.db\.models\.fields')

    with temp_dir() as STATIC_ROOT:
        with temp_dir() as MEDIA_ROOT:

            _make_settings(args, application, settings, STATIC_ROOT, MEDIA_ROOT)

            # run
            if args['test']:
                # make "Address already in use" errors less likely, see Django
                # docs for more details on this env variable.
                os.environ.setdefault(
                    'DJANGO_LIVE_TEST_SERVER_ADDRESS',
                    'localhost:8000-9000'
                )
                if args['--xvfb']:  # pragma: no cover
                    import xvfbwrapper

                    context = xvfbwrapper.Xvfb(width=1280, height=720)
                else:
                    @contextlib.contextmanager
                    def null_context():
                        yield

                    context = null_context()

                with context:
                    num_failures = test(args['<test-label>'], application,
                                        args['--failfast'], args['--runner'])
                    sys.exit(num_failures)
            elif args['shell']:
                shell()
            elif args['compilemessages']:
                compilemessages(application)
            elif args['makemessages']:
                makemessages(application)
            elif args['makemigrations']:
                makemigrations(application)
            elif args['pyflakes']:
                return static_analisys(application)
            elif args['authors']:
                return generate_authors()


def main():  # pragma: no cover
    # Command is executed in the main directory of the plugin, and we must
    # include it in the current path for the imports to work
    sys.path.insert(0, '.')

    args = docopt(__doc__)
    application = args['<application>']
    application_module = import_module(application)
    args = docopt(__doc__, version=application_module.__version__)
    core(args=args, application=application)


if __name__ == '__main__':
    main()
