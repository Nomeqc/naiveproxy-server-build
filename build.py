import builtins
import os
import re
import shlex
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import List, Tuple, Union

old_print = builtins.print


def hook_print():
    """
    hook 系统print 默认flush参数为True
    """

    def my_print(*args, **kwargs):
        # old_print("hooked print")
        if "flush" not in kwargs:
            kwargs["flush"] = True
        old_print(*args, **kwargs)

    builtins.print = my_print


def unhook_print():
    builtins.print = old_print


@contextmanager
def cwd(path):
    wd = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(wd)


def runcmd(
    args: Union[str, List[str]], shell=False, show_window=False, timeout=None
) -> Tuple[str, int]:
    try:
        import shlex
        import subprocess

        if isinstance(args, str):
            if not shell:
                args = shlex.split(args)
        elif isinstance(args, list):
            if shell:
                args = subprocess.list2cmdline(args)
        else:
            raise TypeError(
                f"args type error: {type(args)}, args type must be str or list."
            )

        startupinfo = None
        if os.name == "nt" and not shell and not show_window:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        proc = subprocess.Popen(
            args,
            startupinfo=startupinfo,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            shell=shell,
        )
        stdout, _ = proc.communicate(timeout=timeout)
        retcode = proc.returncode
        stdout = stdout.rstrip(b"\r\n")
        for enc in ["utf-8", "gbk"]:
            try:
                output = stdout.decode(enc)
                return output, retcode
            except Exception:
                pass
        output = stdout.decode("utf-8", errors="ignore")
        return output, retcode
    except Exception as e:
        output = str(e)
        retcode = 2
        return output, retcode


def execute(cmd: str):
    print(f"🛩️ 运行命令: {cmd}")
    try:
        result = subprocess.run(shlex.split(cmd))
        if result.returncode != 0:
            sys.exit(1)
    except Exception as e:
        print(f"❌出错了：{e}")
    # assert result.returncode == 0, "出错了："


def get_caddy_version():
    cmd = "./caddy version"
    out, retcode = runcmd(cmd)
    assert retcode == 0, f"出错了：{out}"
    # out = "v2.8.4 h1:q3pe0wpBj1OcHFZ3n/1nl4V4bxBrYoSoab7rL9BMYNk="
    version = full_version = out.strip()
    result = re.search(r"\S+", version)
    if result:
        version = result.group(0)
    return full_version, version


def get_tags():
    cmd = "git tag --list"
    out, retcode = runcmd(cmd)
    assert retcode == 0, f"出错了：{out}"
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

    execute("go install github.com/caddyserver/xcaddy/cmd/xcaddy@latest")
    execute(
        "xcaddy build --with github.com/caddyserver/forwardproxy=github.com/klzgrad/forwardproxy@naive"
    )
    execute("chmod +x ./caddy")
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
            execute(cmd)

        # 将新tag写入到环境变量文件 以备下一步使用
        set_runner_env_var("NEW_TAG", new_tag)
        set_runner_env_var("FULL_VERSION", full_version)


if __name__ == "__main__":
    hook_print()
    build()
