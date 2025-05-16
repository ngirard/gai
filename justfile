# Generate a directory snapshot for the project
snapshot:
    #!/usr/bin/env bash
    project_name="$(basename "${PWD%.git}")"
    snapshot_filename=".${project_name}_repo_snapshot.md"
    dir2prompt > "${snapshot_filename}"
    wc -c "${snapshot_filename}"

implement_change:
    ./gai.py \
        --conf-system-instruction @:./system/python.j2 \
        --conf-user-instruction @:./gen.git/user/implement_changes.j2 \
        --program @:"$PWD/gai.py" \
        --changes @:./change.md \
        --show-prompt | xclip -selection clipboard

describe_improvement:
    ./gai.py \
        --conf-system-instruction @:./system/python.j2 \
        --conf-user-instruction @:user/describe_improvement.j2 \
        --program @:"$PWD/gai.py" \
        --show-prompt | xclip -selection clipboard
# > next_improvement.md

install:
    sudo install gai.py /usr/local/bin/gai
