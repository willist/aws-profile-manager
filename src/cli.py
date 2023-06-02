import configparser
import logging
from collections import OrderedDict
from pathlib import Path
from functools import partial

import boto3
import click
from click import pass_context
from tabulate import tabulate

from .sso_login import get_sso_token


DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_FILE = Path().joinpath('manage-profiles.log')


def create_logger(ctx):
    logger = logging.getLogger("manage-profiles")
    logger.setLevel(ctx.obj["log_level"])

    # add custom logging filter that adds the command name to the log record
    class CommandFilter(logging.Filter):
        def filter(self, record):
            record.command = ctx.command.name
            return True

    logger.addFilter(CommandFilter())
    formatter = logging.Formatter("%(asctime)s - %(name)s::%(command)s - %(levelname)s- %(message)s")

    file_handler = logging.FileHandler(ctx.obj["log_file"])
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def slugify(value):
    return value.lower().replace(' ', '-')


def get_accounts(start_url, region):
    token = get_sso_token(start_url=start_url, region=region)
    client = boto3.client('sso', region_name=region)
    account_paginator = client.get_paginator('list_accounts')
    return account_paginator.paginate(accessToken=token).search('accountList[].{Name: accountName, Id: accountId}')


def get_roles_for_account(start_url, account_id, region):
    token = get_sso_token(start_url=start_url, region=region)
    client = boto3.client('sso', region_name=region)
    role_paginator = client.get_paginator('list_account_roles')
    return role_paginator.paginate(accessToken=token, accountId=account_id).search('roleList[].roleName')


@click.group()
@click.option('--log-level', default=DEFAULT_LOG_LEVEL, help="The log level to use.", type=click.Choice(logging._nameToLevel.keys()), show_default=True)
@click.option('--log-file', default=DEFAULT_LOG_FILE, help="The log file to write to.", show_default=True)
@click.option(
    '--region',
    envvar="AWS_DEFAULT_REGION",
    show_envvar=True,
    default="us-west-2",
    help="The AWS region to use.",
)
@pass_context
def cli(ctx, log_level, log_file, region):
    """Does cool stuff?"""
    ctx.obj = {
        "log_level": log_level,
        "log_file": log_file,
        "region": region,
    }


@cli.command()
@click.option(
    '--aws-config',
    default=Path().home().joinpath(".aws/config"),
    help="The path to your AWS config file",
    show_default=True,
)
@click.option(
    '--prefix',
    help="String all managed profiles should start with.",
    default=None,
    show_default=True,
)
@pass_context
def list_profiles(ctx, aws_config, prefix):
    """
    Get information about the AWS profiles you have configured.
    """
    logger = create_logger(ctx)

    #log options
    logger.info(f"aws_config: {aws_config}")
    logger.info(f"prefix: {prefix}")

    config = configparser.ConfigParser()
    with open(aws_config) as f:
        config.read_file(f)

    profiles = (p for p in config.sections())
    if prefix is not None:
        profiles = (p for p in profiles if p.startswith(f'profile {prefix}-'))

    data = [
        {
            "Profile": p.removeprefix("profile "),
            "SSO": u'\N{check mark}' if 'sso_start_url' in config[p] else '',
            "Account Id": config[p].get('sso_account_id'),
            "Role": config[p].get('sso_role_name'),
            "MFASerial": config[p].get('mfa_serial'),
            "SSO Region": config[p].get('sso_region'),
            "Region": config[p].get('region'),
        }
        for p in profiles
    ]

    click.echo(tabulate(data, headers="keys"))


@cli.command()
@click.option(
    '--aws-config',
    default=Path().home().joinpath(".aws/config"),
    help="The path to your AWS config file",
    show_default=True,
)
@click.option(
    '--dry-run',
    help="Don't actually make any changes.",
    default=False,
    is_flag=True,
    show_default=True,
)
@pass_context
def sort_profiles(ctx, aws_config, dry_run):
    """
    Sort your AWS config profiles.
    """
    logger = create_logger(ctx)

    logger.info(f"aws_config: {aws_config}")

    input_config = configparser.ConfigParser()
    with Path(aws_config).open() as f:
        input_config.read_file(f)

    output_config = configparser.ConfigParser({}, dict_type=OrderedDict)

    for section in sorted(input_config.sections()):
        output_config[section] = input_config[section]

    if not dry_run:
        with Path(aws_config).open("w") as f:
            output_config.write(f)
    else:
        output_config.write(click.get_text_stream("stdout"))


@cli.command()
@click.option(
    '--start-url',
    required=True,
    envvar="MP_START_URL",
    show_envvar=True,
    help="The start URL for your SSO instance.",
)
@pass_context
def list_accounts(ctx, start_url):
    """
    Get information about the AWS accounts you have access to.
    """
    logger = create_logger(ctx)

    #log options
    logger.info(f"start_url: {start_url}")

    data = []
    with click.progressbar(length=100, fill_char=".", empty_char="", bar_template='Fetching accounts...%(bar)s') as bar:
        for account in get_accounts(start_url, ctx.obj["region"]):
            for role in get_roles_for_account(start_url, account['Id'], ctx.obj["region"]):
                bar.update(1)
                data.append({
                    "Account Name": account['Name'],
                    "Account Id": account['Id'],
                    "Role": role,
                })

    click.echo(tabulate(sorted(data, key=lambda x: str.casefold(x["Account Name"])), headers="keys"))



@cli.command()
@click.option(
    '--start-url',
    required=True,
    envvar="MP_START_URL",
    show_envvar=True,
    help="The start URL for your SSO instance.",
)
@click.option(
    '--aws-config',
    default=Path().home().joinpath(".aws/config"),
    help="The path to your AWS config file",
    show_default=True,
)
@click.option(
    '--prefix',
    help="String all managed profiles should start with.",
    default="sso",
    show_default=True,
)
@click.option(
    '--dry-run',
    help="Don't actually make any changes.",
    default=False,
    is_flag=True,
    show_default=True,
)
@pass_context
def sso_sync(ctx, start_url, aws_config, prefix, dry_run):
    """
    Sync your SSO based AWS accounts as AWS config profiles.
    """
    logger = create_logger(ctx)

    logger.info(f"start_url: {start_url}")
    logger.info(f"aws_config: {aws_config}")
    logger.info(f"prefix: {prefix}")

    # TODO: fix make_backup
    config_obj = configparser.ConfigParser()
    with Path(aws_config).open() as f:
        config_obj.read_file(f)

    existing_sso_profiles = set(s.removeprefix("profile ") for s in config_obj.sections() if s.startswith(f"profile {prefix}-"))

    changes = False
    valid_sso_profiles = set()

    # add new profiles
    for account in get_accounts(start_url, ctx.obj['region']):
        for role in get_roles_for_account(start_url, account['Id'], ctx.obj['region']):
            profile_name = f"{prefix}-{slugify(account['Name'])}-{slugify(role)}"
            valid_sso_profiles.add(profile_name)
            if profile_name not in existing_sso_profiles:
                changes = True
                message = f"Adding profile: {profile_name}"
                logger.info(message)
                click.echo(message)
                config_obj[f"profile {profile_name}"] = {
                    "sso_start_url": start_url,
                    "sso_account_id": account['Id'],
                    "sso_role_name": role,
                    "sso_region": ctx.obj['region'],
                }

    # remove old profiles that match the prefix
    invalid_sso_profiles = existing_sso_profiles - valid_sso_profiles
    for profile in invalid_sso_profiles:
        changes = True
        message = f"Removing profile: {profile}"
        logger.info(message)
        click.echo(message)
        del config_obj[f"profile {profile}"]


    if changes:
        if not dry_run:
            with Path(aws_config).open("w") as f:
                config_obj.write(f)
        else:
            config_obj.write(click.get_text_stream("stdout"))
    else:
        click.echo("No changes to make.")




main = cli()
