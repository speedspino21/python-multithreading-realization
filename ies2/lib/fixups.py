import re
from contextlib import suppress

from .lazy_datatable import LazyDataTables


def skill_specdesc_cleanup(c):
    # Permanent fixes
    c = c.replace('[Stun] Enemy]', '[Stun] Enemy')
    c = c.replace('\\nDamage Amplification for building100% chance to enemy [Siege start]',
                  '\\nDamage Amplification for building')
    c = c.replace('skil\\n', 'skill\\n')
    c = c.replace('coo ldown', 'cool down')
    c = c.replace('ATK Lv.', 'AR')
    c = c.replace('[Lithifify]', '[Petrify]')
    c = c.replace('ATK +1%\\n[Rage]', 'AR +1\\n[Rage]')
    c = c.replace('[Lightening]', '[Lightning]')
    c = c.replace('ignores Enemy DEF -50', 'ignores Enemy DEF by 50')
    c = c.replace('Damage+', 'Damage +')
    c = re.sub(r'(A|D)\.?R\.?', r'\1R', c)
    c = re.sub(r'%([a-zA-Z])', r'% \1', c)
    c = re.sub(r'\\n\s+', r'\\n', c)
    c = c.replace('8gnores', 'Ignores')
    c = c.replace(':[', ': [')

    # Missing feature fixes
    c = c.replace('\\nSkill additional damage in proportion to the caster\'s max HP', '')
    c = c.replace('\\nIn [Destruido] State, additional DEF Ignore according to caster\'s max HP.', '')
    c = c.replace('\\nAccording to [Broken Armor] Lv., additional damage in proportion to PC max HP\\nAccording to '
                  '[Broken Armor] Lv., Monster skill damage increases by 30%', '')
    c = c.replace('\\nApply [Will of field chef] to oneself.', '')
    c = c.replace('\\nWhen enemy is in state of [Fire][Freeze][Ice Wizard][Paralysis][Stun], ignores DEF by 10~40', '')
    c = c.replace('\\nWhen enemy is in state of [Burn][Freeze][Ice Wizard][Paralysis][Stun], ignores DEF by 10~40', '')
    c = c.replace('\\nWhen skill hits, applies [Gold River] to oneself.', '')
    c = c.replace('\\n100% chance to enemy [Siege start]', '')
    c = c.replace(' \\nThe number of people of Max blow increase by 5 in wide area skill', '')
    c = c.replace('\\nSkill ATK rises in proportion to AGI', '')
    c = c.replace('\\nWhen skill adjusted, enemy got [Broken Armor]', '')
    c = c.replace('\\nTo oneself\\nApply [Will of field chef]', '')
    c = c.replace('(Fixed additional damage for monsters)', '')
    c = c.replace('\\nWhen attack enemy of [Pierced Wound] status, cast [Enhance Pierced Wound] by 100%', '')
    return c


fixups = {
    'itemcharge': [
        ('ClassID', -1),      # LazyDataTables will fix class id to be sequential and put it to the end of table
        ('salecost', ''),
        ('cost', '999999')
    ],
    'item': [
        (re.compile('Spec|Desc|ReqToolTip'), lambda c: re.sub(r'(A|D)\.?R\.?', r'\1R', c)),
        ('MonDef', None),
        ('PCDef', None),
        ('InfoView', None),
    ],
    'skill': [
        ('Desc', lambda c: re.sub(r'(A|D)\.?R\.?', r'\1R', c)),
        (re.compile('SpecDesc[0-9]+'), skill_specdesc_cleanup),
        ('PvPFix', lambda c: ('{:.2f}'.format(float(c) / 2)).rstrip('0').rstrip('.')),
        (re.compile('Name|Desc'), lambda c: re.sub('grim-ripper', 'Grim Reaper', c, flags=re.IGNORECASE))
    ],
    'stance': [
        ('Desc', None),
        ('Dummy_A_LH', lambda c: None if c == 'None' else c),
        ('Dummy_A_RH', lambda c: None if c == 'None' else c),
        ('Dummy_N_RH', lambda c: None if c == 'None' else c),
        ('Dummy_N_LH', lambda c: None if c == 'None' else c),
        ('Dummy_F', lambda c: None if c == 'None' else c),
        ('Dummy_B', lambda c: None if c == 'None' else c)
    ]
    # 'fittingroom': {
    #     'Count': lambda c: str(int(int(c) * 2.5))
    # }
}
fixups['skill_worldpvp'] = fixups['skill']


def fixup_cls(datatable, cls):
    modified = False
    if datatable in LazyDataTables.item_datatables:
        datatable = 'item'
    elif datatable in LazyDataTables.monster_datatables:
        datatable = 'monster'
    elif datatable not in fixups:
        return False
    fixup = fixups[datatable]
    for key_find, action in fixup:
        with suppress(KeyError):
            for key in cls.keys():
                if isinstance(key_find, str):
                    match = key == key_find
                else:
                    match = key_find.match(key) is not None

                if match:
                    if action is None:
                        del cls[key]
                    elif isinstance(action, (str, int, float)):
                        action = str(action)
                        if action == '':
                            del cls[key]
                            modified = True
                        else:
                            cls[key] = action
                            modified = True
                    elif callable(action):
                        value = action(cls[key])
                        if value is None:
                            del cls[key]
                            modified = True
                        else:
                            cls[key] = value
                            modified = True
                    elif isinstance(action, tuple):
                        if len(action) != 2:
                            raise ValueError()
                        if isinstance(action[0], str):
                            cls[key] = cls[key].replace(*action)
                            modified = True
                        elif isinstance(action[0], re._pattern_type):
                            cls[key] = re.sub(*action, cls[key])
                            modified = True
                        else:
                            raise ValueError()
    return modified
