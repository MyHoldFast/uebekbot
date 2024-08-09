import os
from babel.messages.pofile import read_po, write_po
from babel.messages.mofile import read_mo

# Путь к папке с локалями
locales_dir = 'locales'

for root, dirs, files in os.walk(locales_dir):
    for file in files:
        if file.endswith('.mo'):
            mo_file = os.path.join(root, file)
            po_file = os.path.splitext(mo_file)[0] + '.po'

            # Читаем .mo файл
            catalog = read_mo(open(mo_file, 'rb'))

            # Записываем .po файл
            with open(po_file, 'wb') as f:
                write_po(f, catalog)
