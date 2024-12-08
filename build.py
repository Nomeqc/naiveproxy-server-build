import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Tuple, Union


@contextmanager
def cwd(path):
    wd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(wd)


def runcmd(
    args: Union[str, Iterable[Union[str, Path]]],
    shell=False,
    console_output=False,
    show_window=False,
    input=None,
    timeout=None,
    check=False,
    **kwargs,
) -> Tuple[str, int]:
    """对subprocess.run的封装，以便更易于使用

    Args:
        args (Union[str, Iterable[Union[str, Path]]]): 命令参数，可以是str,list,tuple等可迭代对象
        shell (bool, optional): 是否用shell执行. Defaults to False.
        show_window (bool, optional): 是否显示控制台，仅windows生效. Defaults to False.
        input (str, optional): 用户输入. Defaults to None.
        console_output (bool, optional): 是否输出到控制台，如果为True，则直接输出到控制台，否则捕获输出作为结果返回 Defaults to False.
        timeout (float, optional): 超时时间. Defaults to None.
        check (bool, optional): 是否检查状态码，不为0则抛出异常. Defaults to False.
    Returns:
        Tuple[str, int]: 返回：(output, returncode)
    """
    try:
        import shlex
        import subprocess

        if isinstance(args, str):
            if os.name == "posix":
                args = shlex.split(args)
        elif isinstance(args, Iterable):
            _args = []
            for item in args:
                if not isinstance(item, (str, Path)):
                    raise TypeError(
                        f"Items in args must be a str or Path, not {type(item)}"
                    )
                _args.append(str(item))
            args = _args
            if os.name == "nt":
                args = subprocess.list2cmdline(args)
        else:
            raise TypeError(f"{type(args)} args is not allowed")

        if os.name == "nt" and not show_window:
            startupinfo = kwargs.get("startupinfo", subprocess.STARTUPINFO())
            if not isinstance(startupinfo, subprocess.STARTUPINFO):
                raise TypeError(
                    f"startupinfo must be a subprocess.STARTUPINFO, not {type(startupinfo)}"
                )
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            kwargs["startupinfo"] = startupinfo

        kwargs["shell"] = shell
        result = subprocess.run(
            args,
            input=input,
            capture_output=not console_output,
            timeout=timeout,
            check=check,
            **kwargs,
        )
        retcode = result.returncode
        if console_output:
            return "", retcode
        stdout = result.stdout + result.stderr
        if stdout[-2:] == b"\r\n":
            stdout = stdout[:-2]
        elif stdout[-1:] == b"\n":
            stdout = stdout[:-1]
        for enc in ["utf-8", "gbk"]:
            try:
                output = stdout.decode(enc)
                return output, retcode
            except Exception:
                pass
        output = stdout.decode("utf-8", errors="ignore")
    except ValueError:
        raise
    except TypeError:
        raise
    except Exception as e:
        if check and isinstance(e, subprocess.CalledProcessError):
            raise
        output = str(e)
        retcode = 2
    return output, retcode


def shell_exec(cmd: str):
    print(f"🛩️ 运行命令: {cmd}")
    try:
        runcmd(cmd, console_output=True, check=True)
    except Exception:
        print("❌出错了：")
        raise


def runcmd_check_error(cmd: str):
    try:
        return runcmd(cmd, check=True)
    except Exception:
        print("❌出错了：")
        raise


def get_caddy_version():
    cmd = "./caddy version"
    out, _ = runcmd_check_error(cmd)
    # out = "v2.8.4 h1:q3pe0wpBj1OcHFZ3n/1nl4V4bxBrYoSoab7rL9BMYNk="
    version = full_version = out.strip()
    result = re.search(r"\S+", version)
    if result:
        version = result.group(0)
    return full_version, version


def get_tags():
    cmd = "git tag --list"
    out, _ = runcmd_check_error(cmd)
    return [item.strip() for item in out.split("\n")]


def generate_new_tag(caddy_version):
    tags = get_tags()
    new_tag = caddy_version
    build_num = 1
    while new_tag in tags:
        new_tag = f"{caddy_version}-{build_num}"
        build_num += 1
    return new_tag


def set_runner_env_var(name, value):
    os.popen(f'echo "{name}={value}" >> $GITHUB_ENV')


def build():
    repo_parent = os.getenv("REPO_PARENT", "")
    github_repo = os.getenv("GITHUB_REPOSITORY", "")

    shell_exec("go install github.com/caddyserver/xcaddy/cmd/xcaddy@latest")
    shell_exec(
        "xcaddy build --with github.com/caddyserver/forwardproxy=github.com/klzgrad/forwardproxy@naive"
    )
    shell_exec("chmod +x ./caddy")
    full_version, short_version = get_caddy_version()
    print(f"full version: {full_version} version: {short_version}")

    with cwd(Path(repo_parent)):
        new_tag = generate_new_tag(short_version)
        download_url = (
            f"https://github.com/{github_repo}/releases/download/{new_tag}/caddy"
        )
        Path("README.md").write_text(
            f"# naiveproxy-server-build\n### caddy最新构建版本：[{new_tag}]({download_url})"
        )
        ref_name = os.getenv("GITHUB_REF_NAME", "")

        cmd_list = [
            "git config --global user.email nomeqc@gmail.com",
            "git config --global user.name Fallrainy",
            "git add README.md",
            'git commit -m "Update README.md"',
            f'git pull --rebase origin "{ref_name}"',
            f'git push origin "{ref_name}"',
            f'git tag "{new_tag}"',
            f'git push origin "{new_tag}"',
        ]
        for cmd in cmd_list:
            shell_exec(cmd)

        # 将新tag写入到环境变量文件 以备下一步使用
        set_runner_env_var("NEW_TAG", new_tag)
        set_runner_env_var("FULL_VERSION", full_version)


if __name__ == "__main__":
    build()
