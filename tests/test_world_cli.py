"""pzdev world: each action's Lua chunk is run against World.lua and the game doubles of test_world_lua."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'cli'))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pzdev import world  # noqa: E402
from test_world_lua import FAKES, WORLD, lupa  # noqa: E402


@unittest.skipIf(lupa is None, 'lupa missing')
class WorldCliTest(unittest.TestCase):
    def setUp(self):
        self.lua = lupa.LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(FAKES)
        self.lua.execute(WORLD.read_text(encoding='utf-8'))
        self.g = self.lua.globals()

    def run_action(self, *argv):
        code = world.code_for(world.build_parser().parse_args(list(argv)))
        chunk = self.lua.eval('loadstring')(code)
        self.assertIsNotNone(chunk, code)
        return chunk()

    def test_position_and_teleport(self):
        self.assertEqual(self.run_action('pos'), (10.5, 20.5, 0))
        self.assertEqual(self.run_action('tp', '30', '40'), 'teleported')
        self.assertEqual((self.g.PLAYER.x, self.g.PLAYER.y), (30, 40))

    def test_items_in_inventory_and_on_the_ground(self):
        self.assertEqual(self.run_action('item', 'Base.TestItem', '3'), '3 x Base.TestItem')
        self.assertEqual(self.run_action('item', 'Base.TestItem', '--at', '15.5', '20.5', '0'), '1 x Base.TestItem')
        self.assertEqual(self.g.ADDED, 4)

    def test_zombies_frozen_and_vehicle_with_key(self):
        self.lua.execute('getAllOutfits = function() return LIST({ "Police" }) end')
        self.lua.execute('addZombiesInOutfit = function(x, y, z, n) local t = {} '
                         'for i = 1, n do t[i] = ZOMBIE(x, y) end; return LIST(t) end')
        self.assertEqual(self.run_action('zombies', '15', '20', '0', '3', '--outfit', 'Police', '--frozen'),
                         '3 zombie(s)')
        self.assertEqual(self.run_action('vehicle', 'Base.TestCar', '20', '20', '--skin', '1', '--key'),
                         'Base.TestCar id 1')
        self.assertEqual(self.g.ADDED, 1)  # the key

    def test_time_weather_night_and_camera(self):
        self.assertEqual(self.run_action('time', '6.5'), 'previous 12')
        self.assertEqual(self.run_action('weather', 'storm', '2'), 'weather storm')
        self.assertEqual((self.g.WEATHER, self.g.HOURS), (3, 2))
        self.assertEqual(self.run_action('weather', 'hold', '--clouds', '0.3'), 'weather held')
        self.assertEqual(self.g.CLIMATE[8].value, 0.3)
        self.assertEqual(self.run_action('night', 'off'), 'night off')
        self.assertEqual(self.run_action('night', '0.8'), 'night 0.8')
        self.assertEqual(self.run_action('zoom', '-1'), 'zoom -1')
        self.assertEqual(self.run_action('speed', '2'), 'applied')

    def test_stats_skills_flags_heal_clean_types(self):
        old = self.run_action('stat', 'Hunger=0')
        self.assertEqual(old['Hunger'], 0.5)
        self.assertEqual(self.run_action('skill', 'Aiming', '5'), 'previous 0')
        self.assertEqual(self.run_action('flags', 'god=on')['god'], False)
        self.assertTrue(self.g.PLAYER.god)
        self.assertEqual(self.run_action('heal'), 'healed')
        self.assertEqual(self.run_action('clean', 'zombies'), '0 removed')
        self.assertEqual(self.run_action('types', 'item', 'test'), ('1 found', 'Base.TestItem'))

    def test_bad_values_are_refused_before_sending(self):
        parser = world.build_parser()
        for argv in (['flags', 'fly=on'], ['flags', 'god=yes'], ['stat', 'Hunger'], ['item', 'Base.Café']):
            with self.assertRaises(ValueError, msg=argv):
                world.code_for(parser.parse_args(argv))

    def test_lua_strings_are_escaped(self):
        self.assertEqual(world.lua_str('a"b\\c'), '"a\\"b\\\\c"')


if __name__ == '__main__':
    unittest.main()
