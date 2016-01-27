# -*- mode: ruby -*-
# vi: set ft=ruby :

# This file was downloaded from https://raw.githubusercontent.com/edx/configuration/master/vagrant/release/fullstack/Vagrantfile
# This includes a full image of edx. The servers and user logins are here:
# https://github.com/edx/configuration/wiki/edx-Full-stack--installation-using-Vagrant-Virtualbox
# Note: this does not use the code from the Cyanna repo.

Vagrant.require_version ">= 1.5.3"

VAGRANTFILE_API_VERSION = "2"

MEMORY = 4096
CPU_COUNT = 2

# map the name of the git branch that we use for a release
# to a name and a file path, which are used for retrieving
# a Vagrant box from the internet.
openedx_releases = {
  "named-release/dogwood.rc" => {
    :name => "dogwood-fullstack-rc2", :file => "20151221-dogwood-fullstack-rc2.box",
  },
  "named-release/dogwood.rc2" => {
    :name => "dogwood-fullstack-rc2", :file => "20151221-dogwood-fullstack-rc2.box",
  },
  "named-release/cypress" => {
    :name => "cypress-fullstack", :file => "cypress-fullstack.box",
  },
  # Birch is deprecated and unsupported
   "named-release/birch.2" => {
     :name => "birch-fullstack-2", :file => "birch-2-fullstack.box",
   },
}
openedx_releases.default = {
  # changing default to what I can guess is the closest to what we have
  :name => "birch-fullstack-2", :file => "birch-2-fullstack.box",
}
rel = ENV['OPENEDX_RELEASE']

Vagrant.configure(VAGRANTFILE_API_VERSION) do |config|

  # Creates an edX fullstack VM from an official release
  config.vm.box     = openedx_releases[rel][:name]
  config.vm.box_url = "http://files.edx.org/vagrant-images/#{openedx_releases[rel][:file]}"

  config.vm.synced_folder  ".", "/vagrant", disabled: true
  config.ssh.insert_key = true

  config.vm.network :private_network, ip: "192.168.33.10"
  config.hostsupdater.aliases = ["preview.localhost"]

  config.vm.provider :virtualbox do |vb|
    vb.customize ["modifyvm", :id, "--memory", MEMORY.to_s]
    vb.customize ["modifyvm", :id, "--cpus", CPU_COUNT.to_s]

    # Allow DNS to work for Ubuntu 12.10 host
    # http://askubuntu.com/questions/238040/how-do-i-fix-name-service-for-vagrant-client
    vb.customize ["modifyvm", :id, "--natdnshostresolver1", "on"]
  end
end
