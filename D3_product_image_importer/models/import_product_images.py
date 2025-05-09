from odoo import models, fields, api
import base64
import tempfile
import requests
import pandas as pd
from PIL import Image
from io import BytesIO
import logging

_logger = logging.getLogger(__name__)

class ImportProductImages(models.TransientModel):
    _name = 'import.product.images'
    _description = 'Import Product Images'

    excel_file = fields.Binary(string="Excel File", required=True)
    filename = fields.Char(string="Filename")

    def action_import(self):
        if not self.excel_file:
            raise UserError("Please upload an Excel file.")

        # Save and read the file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(base64.b64decode(self.excel_file))
            tmp.seek(0)
            df = pd.read_excel(tmp.name)

        for _, row in df.iterrows():
            default_code = str(row.get('default_code')).strip()
            image_url = row.get('image_1920')
            if not default_code or not image_url:
                continue
            try:
                response = requests.get(image_url)
                response.raise_for_status()

                img = Image.open(BytesIO(response.content)).convert("RGB")
                buffer = BytesIO()
                img.save(buffer, format="JPEG")
                image_base64 = base64.b64encode(buffer.getvalue()).decode()

                product = self.env['product.product'].search([('default_code', '=', default_code)], limit=1)
                if product:
                    product.image_1920 = image_base64
                    _logger.info(f"✅ Updated image for {default_code}")
                else:
                    _logger.warning(f"❌ Product not found: {default_code}")
            except Exception as e:
                _logger.error(f"❌ Failed for {default_code}: {e}")
