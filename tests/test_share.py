"""Sharing tests: wire protocol and Share sync over loopback, no GTK windows.

Run: python3 tests/test_share.py -v   (not `-m unittest`: main.py re-execs itself with LD_PRELOAD)
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import main  # noqa: E402


class StubHandler:
    def __init__(self, root):
        self.root = Path(root)
        self.added = {}          # id -> (item, path)
        self.removed = []

    def hostname(self):
        return "stub"

    def wants(self, item_id):
        return item_id not in self.added

    def dest_for(self, item_id):
        return self.root / item_id

    def on_add(self, item, path):
        self.added[item["id"]] = (item, path)

    def abort(self, item_id):
        pass

    def on_remove(self, ids, cleared):
        self.removed.append((ids, cleared))

    def items(self):
        return [item for item, _ in self.added.values()]

    def item(self, item_id):
        return self.added.get(item_id)


class ShareProtocolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.handler = StubHandler(self.root / "recv")
        self.listener = main.Listener("127.0.0.1", 0, self.handler, lambda ip: True)
        self.port = self.listener.sock.getsockname()[1]

    def tearDown(self):
        self.listener.stop()
        self.tmp.cleanup()

    def _file(self, name="a.txt", data=b"hello shelf"):
        p = self.root / name
        p.write_bytes(data)
        return p

    def test_file_roundtrip(self):
        src = self._file()
        item = {"id": "i1", "origin": "omarchy", "name": "a.txt", "dir": False}
        self.assertTrue(main.send_add("127.0.0.1", self.port, item, str(src)))
        got_item, path = self.handler.added["i1"]
        self.assertEqual(got_item["origin"], "omarchy")
        self.assertEqual(Path(path).name, "a.txt")
        self.assertEqual(Path(path).read_bytes(), b"hello shelf")

    def test_dir_roundtrip(self):
        d = self.root / "folder"
        (d / "sub").mkdir(parents=True)
        (d / "sub" / "x.bin").write_bytes(b"\x00\x01")
        item = {"id": "d1", "origin": None, "name": "folder", "dir": True}
        self.assertTrue(main.send_add("127.0.0.1", self.port, item, str(d)))
        _, path = self.handler.added["d1"]
        self.assertTrue(Path(path).is_dir())
        self.assertEqual((Path(path) / "sub" / "x.bin").read_bytes(), b"\x00\x01")

    def test_add_skip_when_known(self):
        src = self._file()
        item = {"id": "i1", "origin": None, "name": "a.txt", "dir": False}
        main.send_add("127.0.0.1", self.port, item, str(src))
        first = self.handler.added["i1"]
        self.assertTrue(main.send_add("127.0.0.1", self.port, item, str(src)))
        self.assertIs(self.handler.added["i1"], first)
        self.assertEqual(len(self.handler.added), 1)

    def test_remove(self):
        self.assertTrue(main.send_remove("127.0.0.1", self.port, ["i1", "i2"], True))
        self.assertEqual(self.handler.removed, [(["i1", "i2"], True)])

    def test_hello(self):
        self.assertEqual(main.ask_hello("127.0.0.1", self.port), "stub")

    def test_state_and_fetch(self):
        src = self._file("b.txt", b"payload")
        item = {"id": "i9", "origin": "omarchy2", "name": "b.txt", "dir": False}
        main.send_add("127.0.0.1", self.port, item, str(src))
        self.assertEqual(main.ask_state("127.0.0.1", self.port), [item])
        got = main.fetch("127.0.0.1", self.port, "i9", self.root / "fetched")
        self.assertIsNotNone(got)
        fetched_item, path = got
        self.assertEqual(fetched_item, item)
        self.assertEqual(Path(path).read_bytes(), b"payload")
        self.assertIsNone(main.fetch("127.0.0.1", self.port, "nope", self.root / "fetched"))

    def test_peer_path_cannot_escape(self):
        src = self._file()
        item = {"id": "e1", "origin": None, "name": "../../evil.txt", "dir": False}
        main.send_add("127.0.0.1", self.port, item, str(src))
        _, path = self.handler.added["e1"]
        self.assertEqual(Path(path).parent, self.root / "recv" / "e1")

    def test_send_to_dead_port_returns_false(self):
        self.listener.stop()
        self.assertFalse(main.send_remove("127.0.0.1", self.port, ["x"], False))
        self.assertIsNone(main.ask_hello("127.0.0.1", self.port))
        self.assertIsNone(main.ask_state("127.0.0.1", self.port))


class FakeApp:
    def __init__(self):
        self.cfg = {"share": True}
        self.shelf = main.Shelf()

    def refresh_peers(self):
        return False


class ShareSyncTest(unittest.TestCase):
    """A real Share (this machine at 127.0.0.2) against a stub peer at 127.0.0.1:PORT."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.peer = StubHandler(self.root / "peer")
        self.peer_listener = main.Listener("127.0.0.1", main.PORT, self.peer, lambda ip: True)
        status = {"Self": {"UserID": 1, "HostName": "me", "TailscaleIPs": ["127.0.0.2"]},
                  "Peer": {"k": {"UserID": 1, "HostName": "peer", "Online": True,
                                 "TailscaleIPs": ["127.0.0.1"]},
                           "x": {"UserID": 2, "HostName": "stranger", "Online": True,
                                 "TailscaleIPs": ["127.0.0.3"]}}}
        self._orig_status = main.tailscale_status
        main.tailscale_status = lambda: status
        self.app = FakeApp()
        self.share = main.Share(self.app)
        self.share.root = self.root / "mine"
        self.app.shelf.on_local_add.append(self.share.push_add)
        self.app.shelf.on_local_remove.append(self.share.push_remove)

    def tearDown(self):
        main.tailscale_status = self._orig_status
        self.share.disable()
        self.peer_listener.stop()
        self.tmp.cleanup()

    def _until(self, cond, timeout=5.0):
        ctx = main.GLib.MainContext.default()
        end = main.time.time() + timeout
        while not cond() and main.time.time() < end:
            ctx.iteration(False)
            main.time.sleep(0.01)
        return cond()

    def test_startup_pulls_peer_items(self):
        src = self.root / "p.txt"
        src.write_bytes(b"from peer")
        self.peer.added["p1"] = ({"id": "p1", "origin": "peer", "name": "p.txt", "dir": False},
                                 str(src))
        self.share.enable()
        self.assertTrue(self._until(lambda: self.app.shelf.path_for("p1")))
        path = self.app.shelf.path_for("p1")
        self.assertEqual(Path(path).read_bytes(), b"from peer")
        self.assertEqual(self.app.shelf.meta[path]["origin"], "peer")
        self.assertEqual(len(self.peer.added), 1)       # not echoed back as a new item

    def test_enable_offers_my_items(self):
        mine = self.root / "m.txt"
        mine.write_bytes(b"mine")
        self.app.cfg["share"] = False
        self.app.shelf.add(str(mine))
        self.app.cfg["share"] = True
        self.share.enable()
        self.assertTrue(self._until(lambda: len(self.peer.added) == 1))
        item, _ = next(iter(self.peer.added.values()))
        self.assertEqual(item["origin"], "me")

    def test_local_add_and_remove_are_pushed(self):
        f = self.root / "x.txt"
        f.write_bytes(b"x")
        self.app.shelf.add(str(f))
        self.assertTrue(self._until(lambda: len(self.peer.added) == 1))
        item_id = self.app.shelf.meta[str(f)]["id"]
        self.app.shelf.remove([str(f)])
        self.assertTrue(self._until(lambda: self.peer.removed == [([item_id], False)]))

    def test_remote_changes_are_not_echoed(self):
        f = self.root / "r.txt"
        f.write_bytes(b"r")
        self.app.shelf.add(str(f), "r1", "peer", remote=True)
        self.app.shelf.remove([str(f)], remote=True)
        self._until(lambda: False, timeout=0.5)
        self.assertEqual(self.peer.added, {})
        self.assertEqual(self.peer.removed, [])

    def test_stranger_is_rejected(self):
        self.assertTrue(self.share._ensure_listener())
        self.assertFalse(self.share._allow("127.0.0.3"))
        self.assertTrue(self.share._allow("127.0.0.1"))

    def test_off_means_no_listener(self):
        self.app.cfg["share"] = False
        self.assertFalse(self.share._ensure_listener())
        self.assertIsNone(self.share.listener)


if __name__ == "__main__":
    unittest.main()
