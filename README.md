A simple tool to help manage aws sso profiles.

## Installation

1. Clone this repo
2. Use python to install
   `pip install .`

## Quick Start

```
# Set the Start URL
export AWS_SSO_START_URL=https://<your subdomain>.awsapps.com/start

# Set the sso region
export AWS_DEFAULT_REGION=us-west-2

# View the help text
aws-profile-manager
```

## Shell Autocomplete

### Bash

Add this to ~/.bashrc

```
eval "$(_AWS_PROFILE_MANAGER_COMPLETE=bash_source aws-profile-manager)"
```

### Zsh

Add this to ~/.zshrc

```
eval"$(_AWS_PROFILE_MANAGER_COMPLETE=zsh_source aws-profile-manager)"
```

### Fish

Add this to Add this to ~/.config/fish/completions/aws-profile-manager.fish:

```
eval (env _AWS_PROFILE_MANAGER_COMPLETE=fish_source aws-profile-manager)
```
