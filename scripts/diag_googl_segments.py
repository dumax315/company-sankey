from sankey.cli import _config_path, _fetch_quarter_source
from sankey.discovery import discover_filings
from sankey.sec import load_json

ua = "Theodore Halpern theomhalpern@gmail.com"
config = load_json(_config_path("GOOGL", None))
disc = discover_filings(config, quarters=30, from_quarter="2026Q2", user_agent=ua)
config["quarters"].update(disc["quarters"])

RC = {"Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"}

def get(q):
    ex = _fetch_quarter_source(config, q, ua)
    c = config["quarters"][q]; s,e = c["start_date"], c["end_date"]
    facts=ex["facts"]
    def find(concept=None, dims=None, seg=None, prod=None):
        for it in facts:
            if it.get("start_date")!=s or it.get("end_date")!=e: continue
            if concept and it.get("concept")!=concept: continue
            d=it.get("dimensions",{})
            if seg is not None and d.get("us-gaap:StatementBusinessSegmentsAxis")!=seg: continue
            if prod is not None and d.get("srt:ProductOrServiceAxis")!=prod: continue
            if dims is not None and d!=dims: continue
            try: return int(float(it["value"])/1e6)
            except: return None
        return None
    return find

for q, era in [("2025Q2","modern"),("2021Q2","2021"),("2020Q2","2020"),("2019Q2","2019")]:
    f = get(q)
    consolidated = f(concept="Revenues", dims={}) or f(concept="RevenueFromContractWithCustomerExcludingAssessedTax", dims={})
    hedging = f(concept="RevenueNotFromContractWithCustomer", dims={}) or 0
    rows=[]
    if era=="modern":
        segG="goog:GoogleServicesMember"
        rows=[("Search & other",f(seg=segG,prod="goog:GoogleSearchOtherMember")),
              ("YouTube ads",f(seg=segG,prod="goog:YouTubeAdvertisingRevenueMember")),
              ("Google Network",f(seg=segG,prod="goog:GoogleNetworkMember")),
              ("Subscriptions/platforms/devices",f(seg=segG,prod="goog:SubscriptionsPlatformsAndDevicesRevenueMember")),
              ("Google Cloud",f(seg="goog:GoogleCloudMember",prod=None)),
              ("Other Bets",f(seg="us-gaap:AllOtherSegmentsMember",prod=None))]
    elif era=="2021":
        segG="goog:GoogleServicesSegmentMember"
        rows=[("Search & other",f(seg=segG,prod="goog:GoogleSearchOtherMember")),
              ("YouTube ads",f(seg=segG,prod="goog:YouTubeAdvertisingRevenueMember")),
              ("Google Network",f(seg=segG,prod="goog:GoogleNetworkMember")),
              ("Google other",f(seg=segG,prod="goog:OtherRevenuesMember")),
              ("Google Cloud",f(seg="goog:GoogleCloudSegmentMember",prod=None)),
              ("Other Bets",f(seg="us-gaap:AllOtherSegmentsMember",prod=None))]
    elif era=="2020":
        segG="goog:GoogleInc.Member"
        rows=[("Search & other",f(seg=segG,prod="goog:GoogleSearchOtherMember")),
              ("YouTube ads",f(seg=segG,prod="goog:YouTubeAdvertisingRevenueMember")),
              ("Google Network",f(seg=segG,prod="goog:GoogleNetworkMembersPropertiesMember")),
              ("Google Cloud",f(seg=segG,prod="goog:GoogleCloudMember")),
              ("Google other",f(seg=segG,prod="goog:OtherRevenuesMember")),
              ("Other Bets",f(seg="us-gaap:AllOtherSegmentsMember",prod=None))]
    else: # 2019
        segG="goog:GoogleInc.Member"
        rows=[("Google Properties",f(seg=segG,prod="goog:GooglePropertiesMember")),
              ("Google Network",f(seg=segG,prod="goog:GoogleNetworkMembersPropertiesMember")),
              ("Google other",f(seg=segG,prod="goog:OtherRevenuesMember")),
              ("Other Bets",f(seg="us-gaap:AllOtherSegmentsMember",prod=None))]
    s=sum(v for _,v in rows if v)
    print("="*60, q, era)
    for n,v in rows: print(f"   {str(v):>8}  {n}")
    print(f"   hedging={hedging} consolidated={consolidated}")
    print(f"   leaves={s}  leaves+hedging={s+hedging}  diff={None if consolidated is None else s+hedging-consolidated}")
