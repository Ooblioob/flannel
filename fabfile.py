from fabric.api import *
from fabric.contrib.console import confirm
from fabric.colors import red
from sysconfig import *
import yaml
import os

# Read from YAML
def get_config():
  config = file('config.yaml')
  data = yaml.load(config)
  return data

def get_servers():
  data = get_config()
  return data['Servers']

def get_plugins():
  data = get_config()
  if data.has_key('Plugins'):
    return data['Plugins']
  else:
    return None

def get_vcs():
  data = get_config()
  return data['VCS']

def get_themes():
  data = get_config()
  return data['Themes']

# Set servers dynamically
servers = get_servers()
for s in servers:
  print(s)
  address = s
  user = servers[s]['user']
  full_addr = "%s@%s" % (user, address)
  if servers[s].has_key('port'):
    full_addr += ':%s' % servers[s]['port']
  env.hosts.append(full_addr)

# Actual flannel
def check_for_wp_cli(host):
  servers = get_servers()
  server = servers[host]['wp-cli']
  
  if server is None:
    sys.exit('You should install wp-cli, it\'s damn handy.')
  else:
    return server

def check_wp_version(wp_dir):
  with cd(wp_dir):
    v = run('wp core version')
  config = get_config()
  version = config['Application']['WordPress']['version'] 
  if v == version:
    puts('WordPress is okay!')
  else:
    upgrade_wordpress(wp_dir, version)

def check_wp_extensions(wp_dir, extn):
  extension = plugin_or_theme(extn)
  for p in extension:
    with cd(wp_dir):
      extn_path = run('wp %s path %s' % (extn, p))
      extn_index = extn_path.rfind('/')
      extn_dir = extn_path[:extn_index]
      version = extension[p]['version']
      try:
        run('wp %s is-installed %s' % (extn, p))
      except SystemExit:
        install_extension(wp_dir, version, p, extn, extn_dir)
      v = run('wp %s get %s --field=version' % (extn, p))
      if str(v) == str(version):
        print('%s %s is okay!' % (extn, p))
      elif v > version:
        downgrade_extension(wp_dir, version, p, extn, extn_dir)
      else:
        upgrade_extension(wp_dir, version, p, extn, extn_dir)
      if extn == 'theme':
        if run('wp option get template') == p:
          active = 'active'
      else:
        active = run('wp plugin get %s --field=status' % (p))
      if str(active) != 'active':
        run('wp %s activate %s' % (extn, p))

def install_wordpress(version, host):
  try:
    sudo('wp core download --version=%s --allow-root' % (version))
    print('WordPress installed successfully, moving on to configuration.')
  except SystemExit:
    print(red('WordPress failed to install!'))
  config = get_servers()
  wp_config = config[host]['wp-config']
  extra_config = config[host]['extra-config']
  try:
    sudo('cp %s wp-config.php' % (wp_config))
    sudo('cp -R %s configurations' % (extra_config))
    sudo('chmod -R +x configurations')
    sudo('find . -iname \*.php | xargs chmod +x')
    print('WordPress fully configured.')
  except SystemExit:
    print(red('WordPress was not properly configured!'))

def install_extension(extn, host):
  extension = plugin_or_theme(extn)
  failures = []
  for p in extension:
    v = extension[p]['version']
    if extension[p]['src'] != False:
      with cd('wp-content/%ss' % (extn)):
        src = extension[p]['src']
        try:
          git_clone(extn, p, src)
        except SystemExit:
          pass
        try:
          with cd(p):
            sudo('git stash')
            sudo('git fetch origin')
            sudo('git checkout origin/%s' % (v))
        except SystemExit:
          print(red('Failed to update %s' % p))
          failures.append(p)
    else:
      with cd('wp-content/%ss' % (extn)):
        try:
          sudo('svn co --force http://plugins.svn.wordpress.org/%s/tags/%s/ %s' % (p, v, p))
        except SystemExit:
          failures.append(p)
  return failures

def git_clone(extn, p, src):
  extension = plugin_or_theme(extn)
  vcs = get_vcs()
  if extension[p].has_key('vcs_user'):
    origin = extension[p]['vcs_user']
  else:
    origin = vcs[src]['user']
  url = vcs[src]['url']
  sudo('git clone %s/%s/%s.git' % (url, origin, p))

def plugin_or_theme(extn):
  if extn == 'plugin':
    extension = get_plugins()
  elif extn == 'theme':
    extension = get_themes()
  else:
    sys.exit('Either plugin or theme must be set to True.')
  return extension

def deploy():
  servers = get_servers()
  host = env.host_string
  if host[:7] == 'vagrant':
  	env.user = 'vagrant'
  	env.password = 'vagrant'
  	env.host_string = '127.0.0.1'
  else:
	key = '%s_pass' % ( host )
	env.password = os.environ[key]
  index = host.index('@')
  index = index + 1
  port = host.find(':')
  if port > -1 < len(host):
    host = host[index:port]
  else:
    host = host[index:]
  wp_dir = servers[host]['wordpress']
  wp_cli = check_for_wp_cli(host)
  themes = get_themes()
  plugins = get_plugins()
  config = get_config()
  sudoer = servers[host]['sudo_user']
  with settings(path=wp_cli, behavior='append', sudo_user=sudoer):
    sudo('cp -R %s /tmp/build' % wp_dir)
    with cd('/tmp/build'):
      wp_version = config['Application']['WordPress']['version']
      try:
        install_wordpress(wp_version, host)
      except SystemExit:
        pass
      if plugins is not None:
        import pdb; pdb.set_trace()
        plugins_f = install_extension(extn = 'plugin', host = host)
      if themes is not None:
        themes_f = install_extension(extn = 'theme', host=host)
  failures = plugins_f + themes_f
  if len(failures) > 0:
    print(red('The following extensions failed to update:'))
    for f in failures:
      print(f)
  else:
    puts('All done, ready to copy!')
    sudo('cp -R /tmp/build %s' % wp_dir)
    # with cd(wp_dir):
    #   toggle_extensions()
    sudo('rm -rf /tmp/build')