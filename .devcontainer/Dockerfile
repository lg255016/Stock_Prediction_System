# GOV-03: 基底映像由浮動標籤收斂至實測 digest。
#
# 原本: mcr.microsoft.com/devcontainers/python:3-3.14-trixie
#   該標籤（以及 3.14-trixie）都會在 3.14.x patch 版本間浮動，
#   且 registry 未提供 patch 級標籤（3.14.6-trixie 等經實測不存在），
#   因此唯一能釘選到實測版本的方式是 digest。
#
# 實測（GOV-03, 2026-08-23，經淨重建驗證）:
#   Python 3.14.6 (main, Jul 14 2026, 04:42:00) [GCC 14.2.0]
#   digest 於當時同時對應 3-3.14-trixie 與 3.14-trixie 兩個標籤
#
# 取捨: digest 釘選不會自動取得基底映像的安全性更新。
#       更新基底需為刻意動作：改 digest -> 重新產生 requirements.lock.txt
#       -> 執行淨重建驗證（見 CLAUDE.md §13.6）。
FROM mcr.microsoft.com/devcontainers/python@sha256:f04a1e9c29e371436d6086908eed22ac0ba087bae0f8edb826838283cf3d1726
ENV PYTHONUNBUFFERED 1

# [Optional] If your requirements rarely change, uncomment this section to add them to the image.
# COPY requirements.txt /tmp/pip-tmp/
# RUN pip3 --disable-pip-version-check --no-cache-dir install -r /tmp/pip-tmp/requirements.txt \
#    && rm -rf /tmp/pip-tmp

# [Optional] Uncomment this section to install additional OS packages.
# RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
#     && apt-get -y install --no-install-recommends <your-package-list-here>



