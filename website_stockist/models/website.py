"""Per-site settings for the stockist directory.

The call to action is a site-level decision, not a per-stockist one, so it lives
here rather than on the content rows. Each brand gets to ask in its own voice —
"Become a stockist", "Stock Rocko's", "Wholesale enquiries" — because the same
sentence on five sites is the thing that makes a group of brands read as one
template.
"""
from odoo import api, fields, models

DEFAULT_CTA = "Become a stockist"
DEFAULT_HEADING = "Become a stockist"
DEFAULT_SUBMIT = "Send application"


class Website(models.Model):
    _inherit = "website"

    stockist_cta_enabled = fields.Boolean(
        string="Show the stockist call to action", default=True)
    stockist_cta_label = fields.Char(
        string="Call to action label",
        help="The button text on the stockist pages. Say it in this brand's "
             "voice — the same wording on every site is what makes a group of "
             "brands read as one template. Blank uses '%s'." % DEFAULT_CTA,
    )
    stockist_apply_heading = fields.Char(
        string="Application page heading",
        help="The <h1> on /stockists/apply. Keep it separate from the button: a "
             "button says what to do, a heading says what the page is, and "
             '"Click here to..." as a heading reads as an instruction to nobody.',
    )
    stockist_apply_submit_label = fields.Char(
        string="Submit button label",
        help="The button that sends the form. Blank uses '%s'." % DEFAULT_SUBMIT,
    )
    stockist_cta_intro = fields.Text(
        string="Application form intro",
        help="The paragraph above the form. Who you are looking for, and what "
             "happens after they submit.",
    )
    stockist_helpdesk_team_id = fields.Many2one(
        "helpdesk.team",
        string="Stockist enquiry team",
        help="Where applications from this site become tickets. Leave empty and "
             "the module finds the team for this website, then the team for "
             "this website's company.",
    )

    def _stockist_cta_label(self):
        self.ensure_one()
        return (self.stockist_cta_label or "").strip() or DEFAULT_CTA

    def _stockist_apply_heading(self):
        self.ensure_one()
        return (self.stockist_apply_heading or "").strip() or DEFAULT_HEADING

    def _stockist_submit_label(self):
        self.ensure_one()
        return (self.stockist_apply_submit_label or "").strip() or DEFAULT_SUBMIT

    def _stockist_team(self):
        """The helpdesk team an application from this site belongs to.

        Explicit setting first. Then a team pointed at this website — only two
        of the seven teams carry a website_id, so that alone is not enough. Then
        the team for this website's company, which is the mapping that actually
        holds today: every brand site has its own company and its own Customer
        Care team.
        """
        self.ensure_one()
        if self.stockist_helpdesk_team_id:
            return self.stockist_helpdesk_team_id
        Team = self.env["helpdesk.team"].sudo()
        team = Team.search([("website_id", "=", self.id)], limit=1)
        if team:
            return team
        if self.company_id:
            team = Team.search([("company_id", "=", self.company_id.id)], limit=1)
            if team:
                return team
        return Team.browse()
