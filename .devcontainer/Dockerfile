FROM mcr.microsoft.com/devcontainers/base:ubuntu

ARG ASDF_VERSION
COPY .tool-versions.asdf /tmp/.tool-versions.asdf

RUN apt-get update \
    && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y dist-upgrade \
    && apt-get -y install --no-install-recommends htop vim curl git build-essential \
    libffi-dev libssl-dev libxml2-dev libxslt1-dev libjpeg8-dev libbz2-dev \
    zlib1g-dev unixodbc unixodbc-dev libsecret-1-0 libsecret-1-dev libsqlite3-dev \
    openjdk-8-jdk jq apt-transport-https ca-certificates gnupg-agent \
    software-properties-common bash-completion python3-pip make libbz2-dev \
    libreadline-dev libsqlite3-dev wget llvm libncurses5-dev libncursesw5-dev \
    xz-utils tk-dev liblzma-dev netcat-traditional libyaml-dev

# Install ASDF
RUN ASDF_VERSION=$(awk '!/^#/ && NF {print $1; exit}' /tmp/.tool-versions.asdf) && \
    wget -O /tmp/asdf.tar.gz https://github.com/asdf-vm/asdf/releases/download/v${ASDF_VERSION}/asdf-v${ASDF_VERSION}-linux-amd64.tar.gz; \
    tar -xvzf /tmp/asdf.tar.gz; \
    mv asdf /usr/bin

USER vscode

ENV PATH="/home/vscode/.asdf/shims/:$PATH"
RUN \
    echo 'PATH="/home/vscode/.asdf/shims/:$PATH"' >> ~/.bashrc; \
    echo '. <(asdf completion bash)' >> ~/.bashrc; \
    echo '# Install Ruby Gems to ~/gems' >> ~/.bashrc; \
    echo 'export GEM_HOME="$HOME/gems"' >> ~/.bashrc; \
    echo 'export PATH="$HOME/gems/bin:$PATH"' >> ~/.bashrc;

# Install ASDF plugins
RUN asdf plugin add python; \
    asdf plugin add poetry https://github.com/asdf-community/asdf-poetry.git; \
    asdf plugin add shellcheck https://github.com/luizm/asdf-shellcheck.git; \
    asdf plugin add actionlint;

WORKDIR /workspaces/eps-spine-shared
ADD .tool-versions /workspaces/eps-spine-shared/.tool-versions
ADD .tool-versions /home/vscode/.tool-versions

RUN asdf install python; \
    asdf install
