# vim: ft=python fileencoding=utf-8 sts=4 sw=4 et:
# Copyright 2017 Florian Bruhin (The Compiler) <mail@qutebrowser.org>

# This file is part of qutebrowser.
#
# qutebrowser is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# qutebrowser is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with qutebrowser.  If not, see <http://www.gnu.org/licenses/>.

"""Tests for qutebrowser.config.configinit."""

import os
import sys
import logging
import unittest.mock

import pytest

from qutebrowser import qutebrowser
from qutebrowser.config import (config, configexc, configfiles, configinit,
                                configdata, configtypes)
from qutebrowser.utils import objreg, usertypes


@pytest.fixture
def init_patch(qapp, fake_save_manager, monkeypatch, config_tmpdir,
               data_tmpdir):
    monkeypatch.setattr(configfiles, 'state', None)
    monkeypatch.setattr(config, 'instance', None)
    monkeypatch.setattr(config, 'key_instance', None)
    monkeypatch.setattr(config, 'change_filters', [])
    monkeypatch.setattr(configinit, '_init_errors', None)
    monkeypatch.setattr(configtypes.Font, 'monospace_fonts', None)
    yield
    try:
        objreg.delete('config-commands')
    except KeyError:
        pass


@pytest.fixture
def args(fake_args):
    """Arguments needed for the config to init."""
    fake_args.temp_settings = []
    return fake_args


@pytest.fixture(autouse=True)
def configdata_init(monkeypatch):
    """Make sure configdata is init'ed and no test re-init's it."""
    if not configdata.DATA:
        configdata.init()
    monkeypatch.setattr(configdata, 'init', lambda: None)


class TestEarlyInit:

    @pytest.mark.parametrize('config_py', [True, 'error', False])
    def test_config_py(self, init_patch, config_tmpdir, caplog, args,
                       config_py):
        """Test loading with only a config.py."""
        config_py_file = config_tmpdir / 'config.py'

        if config_py:
            config_py_lines = ['c.colors.hints.bg = "red"']
            if config_py == 'error':
                config_py_lines.append('c.foo = 42')
            config_py_file.write_text('\n'.join(config_py_lines),
                                      'utf-8', ensure=True)

        with caplog.at_level(logging.ERROR):
            configinit.early_init(args)

        # Check error messages
        expected_errors = []
        if config_py == 'error':
            expected_errors.append("While setting 'foo': No option 'foo'")

        if configinit._init_errors is None:
            actual_errors = []
        else:
            actual_errors = [str(err)
                             for err in configinit._init_errors.errors]

        assert actual_errors == expected_errors

        # Make sure things have been init'ed
        objreg.get('config-commands')
        assert isinstance(config.instance, config.Config)
        assert isinstance(config.key_instance, config.KeyConfig)

        # Check config values
        if config_py:
            assert config.instance._values == {'colors.hints.bg': 'red'}
        else:
            assert config.instance._values == {}

    @pytest.mark.parametrize('load_autoconfig', [True, False])  # noqa
    @pytest.mark.parametrize('config_py', [True, 'error', False])
    @pytest.mark.parametrize('invalid_yaml', ['42', 'unknown', 'wrong-type',
                                              False])
    def test_autoconfig_yml(self, init_patch, config_tmpdir, caplog, args,
                            load_autoconfig, config_py, invalid_yaml):
        """Test interaction between config.py and autoconfig.yml."""
        # pylint: disable=too-many-locals,too-many-branches
        # Prepare files
        autoconfig_file = config_tmpdir / 'autoconfig.yml'
        config_py_file = config_tmpdir / 'config.py'

        yaml_text = {
            '42': '42',
            'unknown': 'global:\n  colors.foobar: magenta\n',
            'wrong-type': 'global:\n  tabs.position: true\n',
            False: 'global:\n  colors.hints.fg: magenta\n',
        }
        autoconfig_file.write_text(yaml_text[invalid_yaml], 'utf-8',
                                   ensure=True)

        if config_py:
            config_py_lines = ['c.colors.hints.bg = "red"']
            if load_autoconfig:
                config_py_lines.append('config.load_autoconfig()')
            if config_py == 'error':
                config_py_lines.append('c.foo = 42')
            config_py_file.write_text('\n'.join(config_py_lines),
                                      'utf-8', ensure=True)

        with caplog.at_level(logging.ERROR):
            configinit.early_init(args)

        # Check error messages
        expected_errors = []

        if load_autoconfig or not config_py:
            suffix = ' (autoconfig.yml)' if config_py else ''
            if invalid_yaml == '42':
                error = ("While loading data{}: Toplevel object is not a dict"
                        .format(suffix))
                expected_errors.append(error)
            elif invalid_yaml == 'wrong-type':
                error = ("Error{}: Invalid value 'True' - expected a value of "
                        "type str but got bool.".format(suffix))
                expected_errors.append(error)
            elif invalid_yaml == 'unknown':
                error = ("While loading options{}: Unknown option "
                         "colors.foobar".format(suffix))
                expected_errors.append(error)
        if config_py == 'error':
            expected_errors.append("While setting 'foo': No option 'foo'")

        if configinit._init_errors is None:
            actual_errors = []
        else:
            actual_errors = [str(err)
                             for err in configinit._init_errors.errors]

        assert actual_errors == expected_errors

        # Check config values
        if config_py and load_autoconfig and not invalid_yaml:
            assert config.instance._values == {
                'colors.hints.bg': 'red',
                'colors.hints.fg': 'magenta',
            }
        elif config_py:
            assert config.instance._values == {'colors.hints.bg': 'red'}
        elif invalid_yaml:
            assert config.instance._values == {}
        else:
            assert config.instance._values == {'colors.hints.fg': 'magenta'}

    def test_invalid_change_filter(self, init_patch, args):
        config.change_filter('foobar')
        with pytest.raises(configexc.NoOptionError):
            configinit.early_init(args)

    def test_temp_settings_valid(self, init_patch, args):
        args.temp_settings = [('colors.completion.fg', 'magenta')]
        configinit.early_init(args)
        assert config.instance._values['colors.completion.fg'] == 'magenta'

    def test_temp_settings_invalid(self, caplog, init_patch, message_mock,
                                   args):
        """Invalid temp settings should show an error."""
        args.temp_settings = [('foo', 'bar')]

        with caplog.at_level(logging.ERROR):
            configinit.early_init(args)

        msg = message_mock.getmsg()
        assert msg.level == usertypes.MessageLevel.error
        assert msg.text == "set: NoOptionError - No option 'foo'"
        assert 'colors.completion.fg' not in config.instance._values

    @pytest.mark.parametrize('settings, size, family', [
        # Only fonts.monospace customized
        ([('fonts.monospace', '"Comic Sans MS"')], 8, 'Comic Sans MS'),
        # fonts.monospace and font settings customized
        # https://github.com/qutebrowser/qutebrowser/issues/3096
        ([('fonts.monospace', '"Comic Sans MS"'),
          ('fonts.tabs', '10pt monospace'),
          ('fonts.keyhint', '10pt monospace')], 10, 'Comic Sans MS'),
    ])
    @pytest.mark.parametrize('method', ['temp', 'auto', 'py'])
    def test_monospace_fonts_init(self, init_patch, args, config_tmpdir,
                                  method, settings, size, family):
        """Ensure setting fonts.monospace at init works properly.

        See https://github.com/qutebrowser/qutebrowser/issues/2973
        """
        if method == 'temp':
            args.temp_settings = settings
        elif method == 'auto':
            autoconfig_file = config_tmpdir / 'autoconfig.yml'
            lines = ["global:"] + ["  {}: '{}'".format(k, v)
                                   for k, v in settings]
            autoconfig_file.write_text('\n'.join(lines), 'utf-8', ensure=True)
        elif method == 'py':
            config_py_file = config_tmpdir / 'config.py'
            lines = ["c.{} = '{}'".format(k, v) for k, v in settings]
            config_py_file.write_text('\n'.join(lines), 'utf-8', ensure=True)

        configinit.early_init(args)

        # Font
        expected = '{}pt "{}"'.format(size, family)
        assert config.instance.get('fonts.keyhint') == expected
        # QtFont
        font = config.instance.get('fonts.tabs')
        assert font.pointSize() == size
        assert font.family() == family

    def test_monospace_fonts_later(self, init_patch, args):
        """Ensure setting fonts.monospace after init works properly.

        See https://github.com/qutebrowser/qutebrowser/issues/2973
        """
        configinit.early_init(args)
        changed_options = []
        config.instance.changed.connect(changed_options.append)

        config.instance.set_obj('fonts.monospace', '"Comic Sans MS"')

        assert 'fonts.keyhint' in changed_options  # Font
        assert config.instance.get('fonts.keyhint') == '8pt "Comic Sans MS"'
        assert 'fonts.tabs' in changed_options  # QtFont
        assert config.instance.get('fonts.tabs').family() == 'Comic Sans MS'

        # Font subclass, but doesn't end with "monospace"
        assert 'fonts.web.family.standard' not in changed_options

    def test_setting_monospace_fonts_family(self, init_patch, args):
        """Make sure setting fonts.monospace after a family works.

        See https://github.com/qutebrowser/qutebrowser/issues/3130
        """
        configinit.early_init(args)
        config.instance.set_str('fonts.web.family.standard', '')
        config.instance.set_str('fonts.monospace', 'Terminus')

    def test_force_software_rendering(self, monkeypatch, config_stub):
        """Setting force_software_rendering should set the environment var."""
        envvar = 'QT_XCB_FORCE_SOFTWARE_OPENGL'
        monkeypatch.setattr(configinit.objects, 'backend',
                            usertypes.Backend.QtWebEngine)
        monkeypatch.delenv(envvar, raising=False)

        config_stub.val.qt.force_software_rendering = True

        configinit._init_envvars()

        assert os.environ[envvar] == '1'

    def test_force_platform(self, monkeypatch, config_stub):
        envvar = 'QT_QPA_PLATFORM'
        monkeypatch.delenv(envvar, raising=False)

        config_stub.val.qt.force_platform = 'toaster'

        configinit._init_envvars()
        assert os.environ[envvar] == 'toaster'

    @pytest.mark.parametrize('old', ['1', '0', None])
    @pytest.mark.parametrize('configval', [True, False])
    def test_hide_wayland_decoration(self, monkeypatch, config_stub,
                                     old, configval):
        envvar = 'QT_WAYLAND_DISABLE_WINDOWDECORATION'
        if old is None:
            monkeypatch.delenv(envvar, raising=False)
        else:
            monkeypatch.setenv(envvar, old)

        config_stub.val.window.hide_wayland_decoration = configval
        configinit._init_envvars()

        assert os.environ.get(envvar) == ('1' if configval else None)


@pytest.mark.parametrize('errors', [True, False])
def test_late_init(init_patch, monkeypatch, fake_save_manager, args,
                   mocker, errors):
    configinit.early_init(args)
    if errors:
        err = configexc.ConfigErrorDesc("Error text", Exception("Exception"))
        errs = configexc.ConfigFileErrors("config.py", [err])
        monkeypatch.setattr(configinit, '_init_errors', errs)
    msgbox_mock = mocker.patch('qutebrowser.config.configinit.msgbox.msgbox',
                               autospec=True)

    configinit.late_init(fake_save_manager)

    fake_save_manager.add_saveable.assert_any_call(
        'state-config', unittest.mock.ANY)
    fake_save_manager.add_saveable.assert_any_call(
        'yaml-config', unittest.mock.ANY, unittest.mock.ANY)
    if errors:
        assert len(msgbox_mock.call_args_list) == 1
        _call_posargs, call_kwargs = msgbox_mock.call_args_list[0]
        text = call_kwargs['text'].strip()
        assert text.startswith('Errors occurred while reading config.py:')
        assert '<b>Error text</b>: Exception' in text
    else:
        assert not msgbox_mock.called


class TestQtArgs:

    @pytest.fixture
    def parser(self, mocker):
        """Fixture to provide an argparser.

        Monkey-patches .exit() of the argparser so it doesn't exit on errors.
        """
        parser = qutebrowser.get_argparser()
        mocker.patch.object(parser, 'exit', side_effect=Exception)
        return parser

    @pytest.mark.parametrize('args, expected', [
        # No Qt arguments
        (['--debug'], [sys.argv[0]]),
        # Qt flag
        (['--debug', '--qt-flag', 'reverse'], [sys.argv[0], '--reverse']),
        # Qt argument with value
        (['--qt-arg', 'stylesheet', 'foo'],
         [sys.argv[0], '--stylesheet', 'foo']),
        # --qt-arg given twice
        (['--qt-arg', 'stylesheet', 'foo', '--qt-arg', 'geometry', 'bar'],
         [sys.argv[0], '--stylesheet', 'foo', '--geometry', 'bar']),
        # --qt-flag given twice
        (['--qt-flag', 'foo', '--qt-flag', 'bar'],
         [sys.argv[0], '--foo', '--bar']),
    ])
    def test_qt_args(self, config_stub, args, expected, parser):
        """Test commandline with no Qt arguments given."""
        parsed = parser.parse_args(args)
        assert configinit.qt_args(parsed) == expected

    def test_qt_both(self, config_stub, parser):
        """Test commandline with a Qt argument and flag."""
        args = parser.parse_args(['--qt-arg', 'stylesheet', 'foobar',
                                  '--qt-flag', 'reverse'])
        qt_args = configinit.qt_args(args)
        assert qt_args[0] == sys.argv[0]
        assert '--reverse' in qt_args
        assert '--stylesheet' in qt_args
        assert 'foobar' in qt_args

    def test_with_settings(self, config_stub, parser):
        parsed = parser.parse_args(['--qt-flag', 'foo'])
        config_stub.val.qt.args = ['bar']
        assert configinit.qt_args(parsed) == [sys.argv[0], '--foo', '--bar']


@pytest.mark.parametrize('arg, confval, used', [
    # overridden by commandline arg
    ('webkit', 'webengine', usertypes.Backend.QtWebKit),
    # set in  config
    (None, 'webkit', usertypes.Backend.QtWebKit),
])
def test_get_backend(monkeypatch, args, config_stub,
                     arg, confval, used):
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name != 'PyQt5.QtWebKit':
            return real_import(name, *args, **kwargs)
        raise ImportError

    args.backend = arg
    config_stub.val.backend = confval
    monkeypatch.setattr('builtins.__import__', fake_import)

    assert configinit.get_backend(args) == used
