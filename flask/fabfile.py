from fabric.api import *
from fabric.contrib.project import rsync_project as rsync
from fabric.contrib.files import exists

from os.path import join, dirname, abspath
from StringIO import StringIO

env.hosts = ['user@host.uberspace.de']

package_name = 'my_app'  # the package name of your app
domain_name= 'myapp.example.com'  # virtual host (/var/www/virtual/...)
port = '5000'  # preferrably a free one
service_name = package_name  # shouldn't bother you

admin_mails = ['you@example.com']
sender_mail = 'noreply@example.com'

# not really needed
# add some more to save bandwidth
rsync_ignore = '''__pycache__
*.pyc
.git*
fabfile.py
testserver.py'''.split()


### end of config
local_base = dirname(abspath(__file__))
local_package_base = join(local_base, package_name)
local_static = join(local_package_base, 'static')

remote_base = '~/data/{}'.format(package_name)
remote_package_base = join(remote_base, package_name)
remote_virtual = '~/virtual/{}'.format(domain_name)
remote_static = join(remote_virtual, 'static')
service_dir = '~/service/{}'.format(service_name)


@task
def deploy():
    install()
    restart()

@task
def install():
    if not exists(remote_base):
        run('mkdir -p {}'.format(remote_base))
    if not exists('~/virtual'):
        run('ln -s /var/www/virtual/$USER/ ~/virtual')
    if not exists(remote_virtual):
        run('mkdir {}'.format(remote_virtual))

    put(get_asset(asset_htaccess), join(remote_virtual, '.htaccess'))
    put(get_asset(asset_daemonsh), join(remote_base, 'daemon.sh'))
    put(get_asset(asset_configfile), join(remote_base, 'config_{}.py'.format(package_name)))
    with cd(remote_base):
        run('chmod +x daemon.sh')

    rsync(
        local_dir=local_package_base,
        exclude=rsync_ignore,
        remote_dir=remote_base + '/',
        delete=True
    )
    put(join(local_base, 'requirements.txt'), remote_base)
    
    with cd(remote_base):
        if not exists(remote_base + '/env'):
            run('virtualenv-2.7 env --distribute')
            run('. env/bin/pip install gunicorn')
        run('. env/bin/pip install -r ./requirements.txt')
        run('cp -R {}/static {}'.format(remote_package_base, remote_virtual))

@task
def restart():
    if not exists(service_dir):
        with cd(remote_base):
            run('uberspace-setup-service {} $PWD/daemon.sh'.format(service_name))
    run('svc -du {}'.format(service_dir))

asset_htaccess = r'''
RewriteEngine On
RewriteCond %{REQUEST_FILENAME} !-f
RewriteBase /
RewriteRule ^(.*)$ http://localhost:''' + port + '''/$1 [P,L]
RequestHeader set X-Forwarded-Proto https env=HTTPS

Options +FollowSymLinks

<IfModule mod_deflate.c>
    # Insert filter
    SetOutputFilter DEFLATE

    # Netscape 4.x has some problems...
    BrowserMatch ^Mozilla/4 gzip-only-text/html

    # Netscape 4.06-4.08 have some more problems
    BrowserMatch ^Mozilla/4\.0[678] no-gzip

    # MSIE masquerades as Netscape, but it is fine
    # BrowserMatch \bMSIE !no-gzip !gzip-only-text/html

    # NOTE: Due to a bug in mod_setenvif up to Apache 2.0.48
    # the above regex won't work. You can use the following
    # workaround to get the desired effect:
    BrowserMatch \bMSI[E] !no-gzip !gzip-only-text/html

    # Don't compress images
    SetEnvIfNoCase Request_URI \
    \.(?:gif|jpe?g|png)$ no-gzip dont-vary

    # Make sure proxies don't deliver the wrong content
    Header append Vary User-Agent env=!dont-vary
</IfModule>

ErrorDocument 503 "<h1>Bad Gateway</h1>"
'''

asset_daemonsh = r'''
cd {remote_base}
. env/bin/activate
exec gunicorn -w 4 -b 127.0.0.1:{port} config_{package_name}:app
'''.format(remote_base=remote_base, package_name=package_name, port=port)

asset_configfile = '#!/usr/bin/env python'
asset_configfile += '\nfrom {} import mk_app'.format(package_name)
asset_configfile += '\ndomain_name = "{}"'.format(domain_name)
asset_configfile += '\nsender_mail = "{}"'.format(sender_mail)
asset_configfile += '\nadmin_mails = {}'.format(repr(admin_mails))

asset_configfile += r'''
import os
import logging
from logging.handlers import SMTPHandler
from werkzeug.contrib.fixers import ProxyFix
logging.basicConfig(level=logging.WARNING)

app = mk_app({
    'CACHE_TYPE': 'filesystem'
})

app.wsgi_app = ProxyFix(app.wsgi_app)

mail_handler = SMTPHandler('127.0.0.1', sender_mail, admin_mails, '{} failed'.format(domain_name))
mail_handler.setLevel(logging.ERROR)
app.logger.addHandler(mail_handler)
'''

def get_asset(string):
    return StringIO(string)
