# -*- mode: ruby -*-
# vi: set ft=ruby :

# Vagrantfile API/syntax version. Don't touch unless you know what you're doing!
VAGRANTFILE_API_VERSION = "2"

def require_plugin(name, version='>= 0')
  unless Vagrant.has_plugin?(name, version)
    puts "'#{name} is not installed!"
    exit! 1
  end
end

module OS
  def self.mac?
    /darwin/ =~ RbConfig::CONFIG['host_os']
  end

  def self.windows?
    /mswin|mingw|cygwin/ =~ RbConfig::CONFIG['host_os']
  end

  def self.linux?
    /linux/ =~ RbConfig::CONFIG['host_os']
  end
end

$provisioning_script = <<SCRIPT
##
## Sanity check
##
if [[ ! "$(lsb_release -d | cut -f2)" =~ $'Ubuntu 12.04' ]]; then
   echo "This script is only known to work on Ubuntu 12.04, exiting...";
   exit;
fi

##
## Install system pre-requisites
##
sudo apt-get update
sudo apt-get install -y build-essential software-properties-common python-software-properties curl git-core libxml2-dev libxslt1-dev python-pip python-apt python-dev python-augeas gcc swig dialog libxmlsec1 libxmlsec1-dev
sudo pip install --upgrade pip
sudo pip install --upgrade virtualenv

##
## Clone the configuration repository and run Ansible
##
cd /var/tmp
git clone -b release-vagrant https://github.com/cyanna/configuration

##
## Install the ansible requirements
##
cd /var/tmp/configuration
sudo pip install -r requirements.txt
SCRIPT

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|
  # All Vagrant configuration is done here. The most common configuration
  # options are documented and commented below. For a complete reference,
  # please see the online documentation at vagrantup.com.

  # Every Vagrant virtual environment requires a box to build off of.
  config.vm.box = "precise64"

  # The url from where the 'config.vm.box' box will be fetched if it
  # doesn't already exist on the user's system.
  # config.vm.box_url = "http://domain.com/path/to/above.box"

  # Create a forwarded port mapping which allows access to a specific port
  # within the machine from a port on the host machine. In the example below,
  # accessing "localhost:8080" will access port 80 on the guest machine.
  config.vm.network :forwarded_port, guest: 80, host: 8080
  config.vm.network :forwarded_port, guest: 18010, host: 18010

  # Create a private network, which allows host-only access to the machine
  # using a specific IP.
  config.vm.network :private_network, ip: "172.16.88.30"

  # If true, then any SSH connections made will enable agent forwarding.
  # Default value: false
  config.ssh.forward_agent = true

  config.vm.provider :virtualbox do |vb|
    require_plugin 'vagrant-vbguest'

    # Taken from https://github.com/rdsubhas/vagrant-faster/blob/master/lib/vagrant/faster/action.rb
    # We do not use the plugin because its calculations aren't what we want.
    # Assume we start with 4 CPUs and 8G of RAM.
    cpus = 4
    mem = 8096
    begin
      if OS.mac?
        cpus = `sysctl -n hw.physicalcpu`.to_i
        mem = `sysctl -n hw.memsize`.to_i / 1024 / 1024
      elsif OS.linux?
        cpus = `nproc`.to_i
        mem = `grep 'MemTotal' /proc/meminfo | sed -e 's/MemTotal://' -e 's/ kB//'`.to_i / 1024
      elsif OS.windows?
        cpus = `wmic cpu Get NumberOfCores`.split[1].to_i
        mem = `wmic computersystem Get TotalPhysicalMemory`.split[1].to_i / 1024 / 1024
      end
    rescue; end

    vb.cpus   = cpus
    vb.memory = mem / 4
  end

  config.vm.provision 'shell', inline: $provisioning_script

end
