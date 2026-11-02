from workbench.prompt_build import generic, kept_messages


def test_the_same_image_saved_by_two_calls_is_the_same_message(tmp_path):
    (tmp_path / "0003-image-1.png").write_bytes(b"frame")
    (tmp_path / "0004-image-1.png").write_bytes(b"frame")
    (tmp_path / "0004-image-2.png").write_bytes(b"other frame")
    text = {"role": "user", "parts": [{"kind": "text", "text": "Play."}]}
    image = lambda name: {"role": "user", "parts": [{"kind": "image", "file": name}]}
    assert kept_messages([text, image("0003-image-1.png")], [text, image("0004-image-1.png"), text], tmp_path) == 2
    assert kept_messages([text, image("0003-image-1.png")], [text, image("0004-image-2.png")], tmp_path) == 1


def test_grids_and_cell_changes_become_placeholders():
    assert generic("Last action: ACTION1: changed (0,4) 2->5, (1,4) 5->2\nstate=PLAYING\ngrid:\n0 1\n2 3") == \
        "Last action: ACTION1: changed <cells>\nstate=PLAYING\ngrid:\n<grid>\n"
