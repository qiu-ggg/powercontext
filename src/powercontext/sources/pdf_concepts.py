# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Question-side financial vocabulary for page retrieval.

A FinanceBench question names a *concept* ("quick ratio", "inventory turnover",
"capital intensive"); the 10-K page that answers it names the *line items*
("cash and cash equivalents", "receivables", "current liabilities"). The two
vocabularies barely overlap, so a bag-of-words ranker cannot reach the page no
matter how the weights are tuned.

This module carries the bridge: for each trigger token that appears in a
question, the accounting vocabulary a filing uses on the page that answers it.
It is ordinary domain knowledge - no company, page number, figure or answer
appears here, and nothing is keyed by document.
"""

from __future__ import annotations

#: ``"trigger words": "expansion words"``. Every trigger word in a key is looked
#: up independently, so a question that says "liquidity" and one that says
#: "quick" land on the same expansion.
CONCEPT_SOURCE: dict[str, str] = {
    # liquidity and short-term solvency -> the current section of a balance sheet
    "quick liquidity solvency": (
        "cash equivalent receivable current liabilit asset "
        "short term investment marketable securitie prepaid inventorie"
    ),
    # capital intensity -> long-lived assets and the cash spent to keep them
    "capital intensive capex": (
        "property plant equipment depreciation capital expenditure addition long lived"
    ),
    # gross margin family
    "gross": "net revenue sale sold cost good profit",
    # operating margin family
    "operating": "operating income revenue sale sold cost expense",
    # profitability ratios
    "roa": "net income total asset",
    "roe": "net income shareholder stockholder equity",
    # tax
    "tax effective rate": "provision income tax before expense deferred statutory",
    # working-capital turnover
    "inventory turnover sold times": "inventorie cost sale sold good product revenue",
    # legal exposure
    "legal battle litigation proceeding lawsuit contingenc claim": (
        "legal proceeding litigation claim contingenc investigation "
        "regulatory settlement adversel material action"
    ),
    # geographic footprint
    "geograph region geographic": (
        "geographic north america latin europe asia pacific africa "
        "middle east international segment revenue"
    ),
    # restructuring
    "restructuring impairment severance": (
        "restructur impairment charge severance productivity plan"
    ),
    # inorganic growth
    "acquisition acquire merger": (
        "acquisition busines combination purchase price goodwill acquired consideration"
    ),
    # customer base
    "customer concentration primary": (
        "customer concentration net revenue sale account receivable "
        "distributor retailer single significant depend portion largest key major "
        "adverse affect disrupt unable failure regulation competition"
    ),
    # demand cycle
    "cyclical cyclicality seasonality": (
        "cyclical economic condition demand seasonal backlog order"
    ),
    # unit volume and output
    "production deliverie unit output": "production rate deliverie unit aircraft build",
    # shareholder returns
    "dividend repurchase buyback": (
        "dividend share repurchase treasury stock payout common"
    ),
    # debt
    "debt borrowing leverage": (
        "long term debt short borrowing note payable obligation maturitie interest"
    ),
    # segment reporting
    "segment division": "reportable segment net sale operating income region",
    # top-line movement
    "revenue sales growth grew increase decrease drove": (
        "net revenue net sale increase decrease volume price "
        "favorable unfavourable consolidated"
    ),
    # product and service mix
    "product service category portfolio": (
        "product service brand category net sale segment revenue"
    ),
    # property, plant and equipment movement
    "ppne ppe": "property plant equipment capital expenditure depreciation addition",
    # operating expense lines
    "sga wage compensation": (
        "selling general administrative wage compensation benefit net sale restructuring"
    ),
    # balance-sheet size
    "liability liabilities": (
        "total liabilit account payable long term debt current liabilit asset"
    ),
    # interest coverage
    "interest coverage ebit ebitda ebitdar": (
        "interest expense operating income depreciation amortization ebitda"
    ),
    # goodwill and intangibles
    "goodwill intangible": "goodwill intangible impairment amortization",
    # headcount
    "employee headcount personnel": "employee headcount personnel",
    # statement names as a question says them vs. as a filing titles them
    "position financial sheet balance": "balance sheet asset liabilit equity consolidated",
    "income operation earning statement": "income operation earning consolidated statement",
    "cash flow statement": (
        "cash flow operating investing financing activitie consolidated"
    ),
    # "free cash flow" is often written closed up, and the page never repeats it
    "cashflow fcf conversion": (
        "cash flow operating investing financing expenditure net income consolidated"
    ),
    # retirement obligations
    "pension retiree retirement benefit": (
        "pension benefit obligation plan contribution postretirement opeb employer"
    ),
    # one-off items that move net income without belonging to normal operations
    "event unusual one time potential": (
        "gain loss divestiture impairment litigation settlement restructuring "
        "acquisition charge recoverie insurance sale busines"
    ),
}

__all__ = ["CONCEPT_SOURCE"]
