FROM odoo:19.0

# Switch naar root om te kunnen installeren
USER root

# Installeer de python library MET de force-vlag
RUN pip3 install segno --break-system-packages

# Switch terug naar de odoo user voor veiligheid
USER odoo