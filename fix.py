import codecs

with codecs.open('core/telegram_bot.py', 'r', 'utf-8') as f:
    code = f.read()

import re

# 1. Update queue variables
code = re.sub(
    r'q_pets = self._get_pending_queue\(niche="pets"\)\s+total = len\(q_gen\) \+ len\(q_baby\) \+ len\(q_pets\)',
    'q_pets = self._get_pending_queue(niche="pets")\n                q_moda = self._get_pending_queue(niche="moda")\n                q_tenis = self._get_pending_queue(niche="tenis")\n                \n                total = len(q_gen) + len(q_baby) + len(q_pets) + len(q_moda) + len(q_tenis)',
    code
)

# 2. Update message
code = re.sub(
    r'?? Mascotas: \*\*\{len\(q_pets\)\}\*\* en espera\\n\\n',
    '?? Mascotas: **{len(q_pets)}** en espera\\n?? Moda: **{len(q_moda)}** en espera\\n?? Tenis: **{len(q_tenis)}** en espera\\n\\n',
    code
)
code = re.sub(
    r'Mascotas: \*\*\{len\(q_pets\)\}\*\* en espera\\n\\n',
    'Mascotas: **{len(q_pets)}** en espera\\nModa: **{len(q_moda)}** en espera\\nTenis: **{len(q_tenis)}** en espera\\n\\n',
    code
)

# 3. Update keyboard buttons
code = re.sub(
    r'\[\{"text": "([^"]*Mascotas)", "callback_data": "queue_nav_pets"\}\],',
    '[{"text": "\\1", "callback_data": "queue_nav_pets"}],\n                        [{"text": "?? Ver Cola Moda", "callback_data": "queue_nav_moda"}],\n                        [{"text": "?? Ver Cola Tenis", "callback_data": "queue_nav_tenis"}],',
    code
)

with codecs.open('core/telegram_bot.py', 'w', 'utf-8') as f:
    f.write(code)
print('Done!')
