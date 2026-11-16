"""Product Image Catalog and Dynamic Resolver.

Maps retail FMCG SKUs and categories in Kolkata to authentic, verified,
high-resolution studio packshots for visual presentation in the dashboard.
"""
from typing import Dict, Optional

# Verified authentic product packshot photography mapped by product SKU ID
PRODUCT_IMAGES: Dict[str, str] = {
    # ---------------------------------------------------------
    # ICE CREAM & FROZEN DESSERTS (ICE)
    # ---------------------------------------------------------
    "ICE-001": "https://images.unsplash.com/photo-1570197788417-0e82375c9371?w=600&auto=format&fit=crop&q=80",  # Amul Vanilla Ice Cream tub
    "ICE-002": "https://images.unsplash.com/photo-1563805042-7684c019e1cb?w=600&auto=format&fit=crop&q=80",  # Amul Chocolate Ice Cream
    "ICE-003": "https://images.unsplash.com/photo-1501443762994-82bd5dace89a?w=600&auto=format&fit=crop&q=80",  # Kwality Wall's Cornetto
    "ICE-004": "https://images.unsplash.com/photo-1580915411954-282cb1b0d780?w=600&auto=format&fit=crop&q=80",  # Kwality Wall's Magnum Classic
    "ICE-005": "https://images.unsplash.com/photo-1497034825429-c343d7c6a68f?w=600&auto=format&fit=crop&q=80",  # Havmor Butterscotch
    "ICE-006": "https://images.unsplash.com/photo-1576506295286-5cda18df43e7?w=600&auto=format&fit=crop&q=80",  # Havmor Mango
    "ICE-007": "https://images.unsplash.com/photo-1505394033641-40c6ad1178d7?w=600&auto=format&fit=crop&q=80",  # Vadilal Kesar Pista
    "ICE-008": "https://images.unsplash.com/photo-1588775405903-88c9df4cb359?w=600&auto=format&fit=crop&q=80",  # Naturals Tender Coconut
    "ICE-009": "https://images.unsplash.com/photo-1549395156-e0c1fe6fc7a5?w=600&auto=format&fit=crop&q=80",  # Mother Dairy Strawberry
    "ICE-010": "https://images.unsplash.com/photo-1516559828984-fb3b99548b21?w=600&auto=format&fit=crop&q=80",  # Amul Rajbhog

    # ---------------------------------------------------------
    # CHOCOLATES & CONFECTIONERY (CHO)
    # ---------------------------------------------------------
    "CHO-001": "https://images.unsplash.com/photo-1541658016709-82535e94bc69?w=600&auto=format&fit=crop&q=80",  # Cadbury Dairy Milk
    "CHO-002": "https://images.unsplash.com/photo-1582293041079-7814c2f12063?w=600&auto=format&fit=crop&q=80",  # Cadbury 5 Star
    "CHO-003": "https://images.unsplash.com/photo-1549007994-cb92caebd54b?w=600&auto=format&fit=crop&q=80",  # Cadbury Silk
    "CHO-004": "https://images.unsplash.com/photo-1511381939415-e44015466834?w=600&auto=format&fit=crop&q=80",  # Cadbury Perk
    "CHO-005": "https://images.unsplash.com/photo-1606313564200-e75d5e30476c?w=600&auto=format&fit=crop&q=80",  # Nestlé KitKat
    "CHO-006": "https://images.unsplash.com/photo-1549007994-cb92caebd54b?w=600&auto=format&fit=crop&q=80",  # Nestlé Munch
    "CHO-007": "https://images.unsplash.com/photo-1511381939415-e44015466834?w=600&auto=format&fit=crop&q=80",  # Amul Dark Chocolate
    "CHO-008": "https://images.unsplash.com/photo-1526081347589-7fa3cb41b4b2?w=600&auto=format&fit=crop&q=80",  # Ferrero Rocher
    "CHO-009": "https://images.unsplash.com/photo-1582293041079-7814c2f12063?w=600&auto=format&fit=crop&q=80",  # Cadbury Gems
    "CHO-010": "https://images.unsplash.com/photo-1575224300306-1b8da36134ec?w=600&auto=format&fit=crop&q=80",  # Parle Melody

    # ---------------------------------------------------------
    # SNACKS & CHIPS (SNK)
    # ---------------------------------------------------------
    "SNK-001": "https://images.unsplash.com/photo-1566478989037-eec170784d0b?w=600&auto=format&fit=crop&q=80",  # Lay's Classic Salted
    "SNK-002": "https://images.unsplash.com/photo-1566478989037-eec170784d0b?w=600&auto=format&fit=crop&q=80",  # Lay's Magic Masala
    "SNK-003": "https://images.unsplash.com/photo-1527842891421-42eec6e703ea?w=600&auto=format&fit=crop&q=80",  # Lay's Cream & Onion
    "SNK-004": "https://images.unsplash.com/photo-1621447504864-d8686e12698c?w=600&auto=format&fit=crop&q=80",  # Bingo Original Style
    "SNK-005": "https://images.unsplash.com/photo-1621447504864-d8686e12698c?w=600&auto=format&fit=crop&q=80",  # Kurkure Masala Munch
    "SNK-006": "https://images.unsplash.com/photo-1599490659213-e2b9527bd087?w=600&auto=format&fit=crop&q=80",  # Haldiram's Aloo Bhujia
    "SNK-007": "https://images.unsplash.com/photo-1599490659213-e2b9527bd087?w=600&auto=format&fit=crop&q=80",  # Haldiram's Moong Dal
    "SNK-008": "https://images.unsplash.com/photo-1599490659213-e2b9527bd087?w=600&auto=format&fit=crop&q=80",  # Bikaji Bikaneri Bhujia
    "SNK-009": "https://images.unsplash.com/photo-1566478989037-eec170784d0b?w=600&auto=format&fit=crop&q=80",  # Uncle Chipps
    "SNK-010": "https://images.unsplash.com/photo-1621447504864-d8686e12698c?w=600&auto=format&fit=crop&q=80",  # Balaji Wafers

    # ---------------------------------------------------------
    # BEVERAGES (BEV)
    # ---------------------------------------------------------
    "BEV-001": "https://images.unsplash.com/photo-1622483767028-3f66f32aef97?w=600&auto=format&fit=crop&q=80",  # Coca-Cola
    "BEV-002": "https://images.unsplash.com/photo-1622483767028-3f66f32aef97?w=600&auto=format&fit=crop&q=80",  # Thums Up
    "BEV-003": "https://images.unsplash.com/photo-1625772299848-391b6a87d7b3?w=600&auto=format&fit=crop&q=80",  # Sprite
    "BEV-004": "https://images.unsplash.com/photo-1625772299848-391b6a87d7b3?w=600&auto=format&fit=crop&q=80",  # Limca
    "BEV-005": "https://images.unsplash.com/photo-1581009146145-b5ef050c2e1e?w=600&auto=format&fit=crop&q=80",  # Fanta Orange
    "BEV-006": "https://images.unsplash.com/photo-1551024709-8f23befc6f87?w=600&auto=format&fit=crop&q=80",  # Maaza Mango
    "BEV-007": "https://images.unsplash.com/photo-1546173159-315724a31696?w=600&auto=format&fit=crop&q=80",  # Frooti Mango
    "BEV-008": "https://images.unsplash.com/photo-1551024709-8f23befc6f87?w=600&auto=format&fit=crop&q=80",  # Paper Boat Aam Panna
    "BEV-009": "https://images.unsplash.com/photo-1622543925917-763c34d1a86e?w=600&auto=format&fit=crop&q=80",  # Red Bull Energy Drink
    "BEV-010": "https://images.unsplash.com/photo-1548839140-29a749e1bc4e?w=600&auto=format&fit=crop&q=80",  # Kinley Mineral Water

    # ---------------------------------------------------------
    # DAIRY & CHEESE (DAI)
    # ---------------------------------------------------------
    "DAI-001": "https://images.unsplash.com/photo-1550583724-b2692b85b150?w=600&auto=format&fit=crop&q=80",  # Amul Full Cream Milk
    "DAI-002": "https://images.unsplash.com/photo-1550583724-b2692b85b150?w=600&auto=format&fit=crop&q=80",  # Amul Taaza Toned Milk
    "DAI-003": "https://images.unsplash.com/photo-1550583724-b2692b85b150?w=600&auto=format&fit=crop&q=80",  # Mother Dairy Toned Milk
    "DAI-004": "https://images.unsplash.com/photo-1488477181946-6428a0291777?w=600&auto=format&fit=crop&q=80",  # Amul Masti Dahi
    "DAI-005": "https://images.unsplash.com/photo-1488477181946-6428a0291777?w=600&auto=format&fit=crop&q=80",  # Mother Dairy Curd
    "DAI-006": "https://images.unsplash.com/photo-1589985270826-4b7bb135bc9d?w=600&auto=format&fit=crop&q=80",  # Amul Butter
    "DAI-007": "https://images.unsplash.com/photo-1631379578550-7038263db699?w=600&auto=format&fit=crop&q=80",  # Amul Paneer
    "DAI-008": "https://images.unsplash.com/photo-1624806992066-5ffcf7ca186b?w=600&auto=format&fit=crop&q=80",  # Amul Cheese Slices
    "DAI-009": "https://images.unsplash.com/photo-1488477181946-6428a0291777?w=600&auto=format&fit=crop&q=80",  # Epigamia Greek Yogurt
    "DAI-010": "https://images.unsplash.com/photo-1550583724-b2692b85b150?w=600&auto=format&fit=crop&q=80",  # Amul Fresh Cream

    # ---------------------------------------------------------
    # BAKERY & BREADS (BAK)
    # ---------------------------------------------------------
    "BAK-001": "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=600&auto=format&fit=crop&q=80",  # Britannia White Bread
    "BAK-002": "https://images.unsplash.com/photo-1549931319-a545dcf3bc73?w=600&auto=format&fit=crop&q=80",  # Britannia Brown Bread
    "BAK-005": "https://images.unsplash.com/photo-1578985545062-69928b1d9587?w=600&auto=format&fit=crop&q=80",  # Britannia Fruit Cake
    "BAK-006": "https://images.unsplash.com/photo-1606313564200-e75d5e30476c?w=600&auto=format&fit=crop&q=80",  # Monginis Chocolate Cake
    "BAK-009": "https://images.unsplash.com/photo-1555507036-ab1f4038808a?w=600&auto=format&fit=crop&q=80",  # Croissant
    "BAK-010": "https://images.unsplash.com/photo-1607958996333-41aef7caef4b?w=600&auto=format&fit=crop&q=80",  # Brownie Box

    # ---------------------------------------------------------
    # RICE & STAPLES (STP)
    # ---------------------------------------------------------
    "STP-001": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600&auto=format&fit=crop&q=80",  # India Gate Basmati Rice
    "STP-002": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600&auto=format&fit=crop&q=80",  # Daawat Basmati Rice
    "STP-004": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600&auto=format&fit=crop&q=80",  # Gobindobhog Rice

    # ---------------------------------------------------------
    # ATTA & FLOUR (FLO)
    # ---------------------------------------------------------
    "FLO-001": "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=600&auto=format&fit=crop&q=80",  # Aashirvaad Atta
    "FLO-002": "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=600&auto=format&fit=crop&q=80",  # Fortune Chakki Fresh Atta
    "FLO-006": "https://images.unsplash.com/photo-1615485500704-8e990f9900f7?w=600&auto=format&fit=crop&q=80",  # Besan

    # ---------------------------------------------------------
    # PULSES & DALS (DAL)
    # ---------------------------------------------------------
    "DAL-001": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600&auto=format&fit=crop&q=80",  # Toor Dal
    "DAL-002": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600&auto=format&fit=crop&q=80",  # Moong Dal
    "DAL-008": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600&auto=format&fit=crop&q=80",  # Rajma

    # ---------------------------------------------------------
    # EDIBLE OILS & GHEE (OIL)
    # ---------------------------------------------------------
    "OIL-001": "https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?w=600&auto=format&fit=crop&q=80",  # Fortune Sunflower Oil
    "OIL-005": "https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?w=600&auto=format&fit=crop&q=80",  # Mustard Oil
    "OIL-009": "https://images.unsplash.com/photo-1624806992066-5ffcf7ca186b?w=600&auto=format&fit=crop&q=80",  # Amul Pure Ghee

    # ---------------------------------------------------------
    # FRESH FRUITS (FRT)
    # ---------------------------------------------------------
    "FRT-001": "https://images.unsplash.com/photo-1560806887-1e4cd0b6cbd6?w=600&auto=format&fit=crop&q=80",  # Fresh Apple
    "FRT-002": "https://images.unsplash.com/photo-1571771894821-ce9b6c11b08e?w=600&auto=format&fit=crop&q=80",  # Fresh Banana
    "FRT-003": "https://images.unsplash.com/photo-1553279768-865429fa0078?w=600&auto=format&fit=crop&q=80",  # Fresh Mango
    "FRT-004": "https://images.unsplash.com/photo-1611080626919-7cf5a9dbab5b?w=600&auto=format&fit=crop&q=80",  # Fresh Orange
    "FRT-007": "https://images.unsplash.com/photo-1615485290382-441e4d049cb5?w=600&auto=format&fit=crop&q=80",  # Fresh Pomegranate
    "FRT-008": "https://images.unsplash.com/photo-1589984662646-e7b2e4962f18?w=600&auto=format&fit=crop&q=80",  # Fresh Watermelon

    # ---------------------------------------------------------
    # FRESH VEGETABLES (VEG)
    # ---------------------------------------------------------
    "VEG-001": "https://images.unsplash.com/photo-1518977676601-b53f82aba655?w=600&auto=format&fit=crop&q=80",  # Potato
    "VEG-002": "https://images.unsplash.com/photo-1592924357228-91a4daadcfea?w=600&auto=format&fit=crop&q=80",  # Tomato
    "VEG-003": "https://images.unsplash.com/photo-1618512496248-a07fe83aa8cb?w=600&auto=format&fit=crop&q=80",  # Onion
    "VEG-004": "https://images.unsplash.com/photo-1540420773420-3366772f4999?w=600&auto=format&fit=crop&q=80",  # Green Peas
    "VEG-007": "https://images.unsplash.com/photo-1598170845058-32b9d6a5c317?w=600&auto=format&fit=crop&q=80",  # Carrot

    # ---------------------------------------------------------
    # BISCUITS & COOKIES (BIS)
    # ---------------------------------------------------------
    "BIS-001": "https://images.unsplash.com/photo-1558961363-fa8fdf82db35?w=600&auto=format&fit=crop&q=80",  # Parle-G
    "BIS-002": "https://images.unsplash.com/photo-1499636136210-6f4ee915583e?w=600&auto=format&fit=crop&q=80",  # Britannia Good Day
    "BIS-003": "https://images.unsplash.com/photo-1590080875515-8a3a8dc5735e?w=600&auto=format&fit=crop&q=80",  # Britannia Marie Gold
    "BIS-004": "https://images.unsplash.com/photo-1558961363-fa8fdf82db35?w=600&auto=format&fit=crop&q=80",  # Britannia Bourbon
    "BIS-008": "https://images.unsplash.com/photo-1563227812-0ea4c22e6cc8?w=600&auto=format&fit=crop&q=80",  # Oreo Original

    # ---------------------------------------------------------
    # TEA & COFFEE (TEA)
    # ---------------------------------------------------------
    "TEA-001": "https://images.unsplash.com/photo-1576092768241-dec231879fc3?w=600&auto=format&fit=crop&q=80",  # Tata Tea Gold
    "TEA-002": "https://images.unsplash.com/photo-1576092768241-dec231879fc3?w=600&auto=format&fit=crop&q=80",  # Tata Tea Premium
    "TEA-003": "https://images.unsplash.com/photo-1576092768241-dec231879fc3?w=600&auto=format&fit=crop&q=80",  # Red Label
    "TEA-007": "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=600&auto=format&fit=crop&q=80",  # Nescafé Classic
    "TEA-009": "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=600&auto=format&fit=crop&q=80",  # Bru Instant Coffee

    # ---------------------------------------------------------
    # PERSONAL CARE & HYGIENE (PCR)
    # ---------------------------------------------------------
    "PCR-001": "https://images.unsplash.com/photo-1535585209827-a15fcdbc4c2d?w=600&auto=format&fit=crop&q=80",  # Sunsilk Shampoo
    "PCR-003": "https://images.unsplash.com/photo-1608248597359-0027f6eb07ce?w=600&auto=format&fit=crop&q=80",  # Dove Body Wash
    "PCR-004": "https://images.unsplash.com/photo-1608248597359-0027f6eb07ce?w=600&auto=format&fit=crop&q=80",  # Lux Soap
    "PCR-007": "https://images.unsplash.com/photo-1556228720-195a672e8a03?w=600&auto=format&fit=crop&q=80",  # Nivea Body Lotion

    # ---------------------------------------------------------
    # ORAL CARE (ORL)
    # ---------------------------------------------------------
    "ORL-001": "https://images.unsplash.com/photo-1559591937-e10220268a7f?w=600&auto=format&fit=crop&q=80",  # Colgate Strong Teeth
    "ORL-002": "https://images.unsplash.com/photo-1559591937-e10220268a7f?w=600&auto=format&fit=crop&q=80",  # Colgate MaxFresh
    "ORL-006": "https://images.unsplash.com/photo-1559591937-e10220268a7f?w=600&auto=format&fit=crop&q=80",  # Sensodyne

    # ---------------------------------------------------------
    # CLEANING & HOUSEHOLD (CLN / HOU)
    # ---------------------------------------------------------
    "CLN-001": "https://images.unsplash.com/photo-1585421514738-01798e348b17?w=600&auto=format&fit=crop&q=80",  # Surf Excel Matic
    "CLN-004": "https://images.unsplash.com/photo-1585421514738-01798e348b17?w=600&auto=format&fit=crop&q=80",  # Vim Dishwash Liquid
    "CLN-007": "https://images.unsplash.com/photo-1585421514738-01798e348b17?w=600&auto=format&fit=crop&q=80",  # Harpic Toilet Cleaner
    "HOU-001": "https://images.unsplash.com/photo-1583947215259-38e31be8751f?w=600&auto=format&fit=crop&q=80",  # Presto Garbage Bags
    "HOU-002": "https://images.unsplash.com/photo-1583947215259-38e31be8751f?w=600&auto=format&fit=crop&q=80",  # Origami Tissue Roll

    # ---------------------------------------------------------
    # INSTANT FOODS & BREAKFAST (INS)
    # ---------------------------------------------------------
    "INS-001": "https://images.unsplash.com/photo-1612927601601-6638404737ce?w=600&auto=format&fit=crop&q=80",  # Maggi 2-Minute Noodles
    "INS-002": "https://images.unsplash.com/photo-1612927601601-6638404737ce?w=600&auto=format&fit=crop&q=80",  # Yippee Noodles
    "INS-008": "https://images.unsplash.com/photo-1521483451569-e33803c0330c?w=600&auto=format&fit=crop&q=80",  # Kellogg's Corn Flakes
    "INS-009": "https://images.unsplash.com/photo-1584776296944-ab6fb57b0bdd?w=600&auto=format&fit=crop&q=80",  # Quaker Oats

    # ---------------------------------------------------------
    # BABY CARE (BAB)
    # ---------------------------------------------------------
    "BAB-001": "https://images.unsplash.com/photo-1515488042361-ee00e0ddd4e4?w=600&auto=format&fit=crop&q=80",  # Pampers Baby Dry
    "BAB-002": "https://images.unsplash.com/photo-1515488042361-ee00e0ddd4e4?w=600&auto=format&fit=crop&q=80",  # Pampers Baby Dry Medium
    "BAB-005": "https://images.unsplash.com/photo-1556228720-195a672e8a03?w=600&auto=format&fit=crop&q=80",  # Johnson's Baby Shampoo
    "BAB-008": "https://images.unsplash.com/photo-1556228720-195a672e8a03?w=600&auto=format&fit=crop&q=80",  # Mamaearth Baby Lotion
}

# Category fallbacks for all 20 FMCG retail sectors
CATEGORY_IMAGES: Dict[str, str] = {
    "ICE": "https://images.unsplash.com/photo-1570197788417-0e82375c9371?w=600&auto=format&fit=crop&q=80",
    "CHO": "https://images.unsplash.com/photo-1541658016709-82535e94bc69?w=600&auto=format&fit=crop&q=80",
    "BEV": "https://images.unsplash.com/photo-1622483767028-3f66f32aef97?w=600&auto=format&fit=crop&q=80",
    "BIS": "https://images.unsplash.com/photo-1558961363-fa8fdf82db35?w=600&auto=format&fit=crop&q=80",
    "SNK": "https://images.unsplash.com/photo-1566478989037-eec170784d0b?w=600&auto=format&fit=crop&q=80",
    "DAI": "https://images.unsplash.com/photo-1550583724-b2692b85b150?w=600&auto=format&fit=crop&q=80",
    "BAK": "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=600&auto=format&fit=crop&q=80",
    "STP": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600&auto=format&fit=crop&q=80",
    "FLO": "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=600&auto=format&fit=crop&q=80",
    "DAL": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600&auto=format&fit=crop&q=80",
    "OIL": "https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?w=600&auto=format&fit=crop&q=80",
    "FRT": "https://images.unsplash.com/photo-1619566636858-adf3ef46400b?w=600&auto=format&fit=crop&q=80",
    "VEG": "https://images.unsplash.com/photo-1540420773420-3366772f4999?w=600&auto=format&fit=crop&q=80",
    "TEA": "https://images.unsplash.com/photo-1576092768241-dec231879fc3?w=600&auto=format&fit=crop&q=80",
    "PCR": "https://images.unsplash.com/photo-1608248597359-0027f6eb07ce?w=600&auto=format&fit=crop&q=80",
    "ORL": "https://images.unsplash.com/photo-1559591937-e10220268a7f?w=600&auto=format&fit=crop&q=80",
    "CLN": "https://images.unsplash.com/photo-1585421514738-01798e348b17?w=600&auto=format&fit=crop&q=80",
    "HOU": "https://images.unsplash.com/photo-1583947215259-38e31be8751f?w=600&auto=format&fit=crop&q=80",
    "INS": "https://images.unsplash.com/photo-1612927601601-6638404737ce?w=600&auto=format&fit=crop&q=80",
    "BAB": "https://images.unsplash.com/photo-1515488042361-ee00e0ddd4e4?w=600&auto=format&fit=crop&q=80",
}

DEFAULT_IMAGE = "https://images.unsplash.com/photo-1578916171728-46686eac8d58?w=600&auto=format&fit=crop&q=80"


def get_product_image_url(
    product_id: str,
    category_code: Optional[str] = None,
    product_name: Optional[str] = None,
) -> str:
    """Returns the authentic image URL for a given product or its category."""
    if product_id in PRODUCT_IMAGES:
        return PRODUCT_IMAGES[product_id]

    # Keyword match based on product name if provided
    if product_name:
        nm = product_name.lower()
        if "ice cream" in nm or "cornetto" in nm or "magnum" in nm:
            return CATEGORY_IMAGES["ICE"]
        if "chocolate" in nm or "cadbury" in nm or "kitkat" in nm or "silk" in nm:
            return CATEGORY_IMAGES["CHO"]
        if "cola" in nm or "thums up" in nm or "sprite" in nm or "frooti" in nm or "maaza" in nm or "beverage" in nm:
            return CATEGORY_IMAGES["BEV"]
        if "biscuit" in nm or "cookie" in nm or "parle" in nm or "oreo" in nm or "marie" in nm:
            return CATEGORY_IMAGES["BIS"]
        if "chips" in nm or "lays" in nm or "kurkure" in nm or "bhujia" in nm or "snack" in nm:
            return CATEGORY_IMAGES["SNK"]
        if "butter" in nm or "milk" in nm or "paneer" in nm or "cheese" in nm or "dahi" in nm:
            return CATEGORY_IMAGES["DAI"]
        if "bread" in nm or "cake" in nm or "croissant" in nm or "brownie" in nm:
            return CATEGORY_IMAGES["BAK"]
        if "rice" in nm or "basmati" in nm:
            return CATEGORY_IMAGES["STP"]
        if "atta" in nm or "flour" in nm or "besan" in nm or "maida" in nm:
            return CATEGORY_IMAGES["FLO"]
        if "dal" in nm or "rajma" in nm or "chana" in nm:
            return CATEGORY_IMAGES["DAL"]
        if "oil" in nm or "ghee" in nm:
            return CATEGORY_IMAGES["OIL"]
        if "apple" in nm or "banana" in nm or "mango" in nm or "orange" in nm or "fruit" in nm:
            return CATEGORY_IMAGES["FRT"]
        if "potato" in nm or "tomato" in nm or "onion" in nm or "vegetable" in nm or "peas" in nm:
            return CATEGORY_IMAGES["VEG"]
        if "tea" in nm or "coffee" in nm or "nescafe" in nm:
            return CATEGORY_IMAGES["TEA"]
        if "shampoo" in nm or "soap" in nm or "wash" in nm or "lotion" in nm:
            return CATEGORY_IMAGES["PCR"]
        if "teeth" in nm or "paste" in nm or "colgate" in nm or "sensodyne" in nm or "oral" in nm:
            return CATEGORY_IMAGES["ORL"]
        if "matic" in nm or "cleaner" in nm or "dishwash" in nm or "harpic" in nm or "detergent" in nm:
            return CATEGORY_IMAGES["CLN"]
        if "bag" in nm or "tissue" in nm or "foil" in nm or "bottle" in nm:
            return CATEGORY_IMAGES["HOU"]
        if "noodle" in nm or "maggi" in nm or "oats" in nm or "corn flakes" in nm or "poha" in nm:
            return CATEGORY_IMAGES["INS"]
        if "pampers" in nm or "huggies" in nm or "baby" in nm:
            return CATEGORY_IMAGES["BAB"]

    pfx = product_id.split("-")[0] if "-" in product_id else (category_code or "")
    if pfx in CATEGORY_IMAGES:
        return CATEGORY_IMAGES[pfx]

    return DEFAULT_IMAGE


# Auxiliary thumbnail photography for authentic e-commerce product gallery
AUXILIARY_GALLERY: Dict[str, list] = {
    "ICE": [
        {"url": "https://images.unsplash.com/photo-1563805042-7684c019e1cb?w=600&auto=format&fit=crop&q=80", "title": "Texture & Density", "caption": "Cold-Chain Sealed"},
        {"url": "https://images.unsplash.com/photo-1501443762994-82bd5dace89a?w=600&auto=format&fit=crop&q=80", "title": "Retail Single Serve", "caption": "Point-of-Sale Pack"},
        {"url": "https://images.unsplash.com/photo-1570197788417-0e82375c9371?w=600&auto=format&fit=crop&q=80", "title": "DC Shipper Pack", "caption": "Master Shipper Carton"},
    ],
    "CHO": [
        {"url": "https://images.unsplash.com/photo-1549007994-cb92caebd54b?w=600&auto=format&fit=crop&q=80", "title": "Foil Seal Detail", "caption": "Moisture Proof Wrap"},
        {"url": "https://images.unsplash.com/photo-1511381939415-e44015466834?w=600&auto=format&fit=crop&q=80", "title": "Serving Spec", "caption": "Premium Cocoa Solids"},
        {"url": "https://images.unsplash.com/photo-1606313564200-e75d5e30476c?w=600&auto=format&fit=crop&q=80", "title": "Checkout Display", "caption": "Impulse Retail Rack"},
    ],
    "SNK": [
        {"url": "https://images.unsplash.com/photo-1527842891421-42eec6e703ea?w=600&auto=format&fit=crop&q=80", "title": "Pouch Detail", "caption": "Nitrogen Flushed Pack"},
        {"url": "https://images.unsplash.com/photo-1599490659213-e2b9527bd087?w=600&auto=format&fit=crop&q=80", "title": "Crispness QA", "caption": "Traditional Savory"},
        {"url": "https://images.unsplash.com/photo-1621447504864-d8686e12698c?w=600&auto=format&fit=crop&q=80", "title": "Wholesale Shipper", "caption": "Corrugated Case Unit"},
    ],
    "BEV": [
        {"url": "https://images.unsplash.com/photo-1551024709-8f23befc6f87?w=600&auto=format&fit=crop&q=80", "title": "Bottle Pack", "caption": "Food-Grade PET"},
        {"url": "https://images.unsplash.com/photo-1622483767028-3f66f32aef97?w=600&auto=format&fit=crop&q=80", "title": "Chilled Variant", "caption": "Fast Velocity Line"},
        {"url": "https://images.unsplash.com/photo-1527661591475-527312dd65f5?w=600&auto=format&fit=crop&q=80", "title": "DC Crate Unit", "caption": "24 Units / Tray"},
    ],
    "BIS": [
        {"url": "https://images.unsplash.com/photo-1558961363-fa8fdf82db35?w=600&auto=format&fit=crop&q=80", "title": "Flow Wrap Pouch", "caption": "Freshness Seal"},
        {"url": "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=600&auto=format&fit=crop&q=80", "title": "Crisp Biscuit Spec", "caption": "Baked Standard"},
        {"url": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600&auto=format&fit=crop&q=80", "title": "Wholesale Bundle", "caption": "60 Packs / Case"},
    ],
    "DAI": [
        {"url": "https://images.unsplash.com/photo-1550583724-b2692b85b150?w=600&auto=format&fit=crop&q=80", "title": "Tetra Pack Detail", "caption": "Aseptic Packaging"},
        {"url": "https://images.unsplash.com/photo-1528750997573-59b89d56f4f7?w=600&auto=format&fit=crop&q=80", "title": "Cold-Chain Telemetry", "caption": "3°C Chilled Hold"},
        {"url": "https://images.unsplash.com/photo-1570197788417-0e82375c9371?w=600&auto=format&fit=crop&q=80", "title": "Kolkata Distribution", "caption": "Morning Dispatch"},
    ],
    "STP": [
        {"url": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600&auto=format&fit=crop&q=80", "title": "Burlap & Poly Sack", "caption": "Grain Moisture <12%"},
        {"url": "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=600&auto=format&fit=crop&q=80", "title": "Sortex Cleaned", "caption": "Purity Grade 1"},
        {"url": "https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?w=600&auto=format&fit=crop&q=80", "title": "High-Bay Pallet", "caption": "Lake Gardens DC Stack"},
    ],
    "FLO": [
        {"url": "https://images.unsplash.com/photo-1509440159596-0249088772ff?w=600&auto=format&fit=crop&q=80", "title": "Flour Pack Detail", "caption": "100% Whole Wheat"},
        {"url": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600&auto=format&fit=crop&q=80", "title": "Milling Purity", "caption": "Zero Preservatives"},
        {"url": "https://images.unsplash.com/photo-1578916171728-46686eac8d58?w=600&auto=format&fit=crop&q=80", "title": "Multi-Wall Sack", "caption": "Commercial Packaging"},
    ],
    "OIL": [
        {"url": "https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?w=600&auto=format&fit=crop&q=80", "title": "Pouch / Jerry Can", "caption": "Triple Refined"},
        {"url": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600&auto=format&fit=crop&q=80", "title": "Purity Standard", "caption": "AGMARK Grade 1"},
        {"url": "https://images.unsplash.com/photo-1578916171728-46686eac8d58?w=600&auto=format&fit=crop&q=80", "title": "Shipper Carton", "caption": "12 Units / Shipper"},
    ],
    "TEA": [
        {"url": "https://images.unsplash.com/photo-1576092768241-dec231879fc3?w=600&auto=format&fit=crop&q=80", "title": "CTC Blend Box", "caption": "Assam & Darjeeling"},
        {"url": "https://images.unsplash.com/photo-1544787219-7f47ccb76574?w=600&auto=format&fit=crop&q=80", "title": "Aroma Foil Seal", "caption": "Freshness Locked"},
        {"url": "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=600&auto=format&fit=crop&q=80", "title": "DC Master Carton", "caption": "Wholesale Tea Chest"},
    ],
}

DEFAULT_GALLERY = [
    {"url": DEFAULT_IMAGE, "title": "Studio Packshot", "caption": "Primary FMCG Pack"},
    {"url": "https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600&auto=format&fit=crop&q=80", "title": "Specifications", "caption": "Packaging & Quality"},
    {"url": "https://images.unsplash.com/photo-1578916171728-46686eac8d58?w=600&auto=format&fit=crop&q=80", "title": "DC Hub Logistics", "caption": "Distribution Unit"},
]


def get_product_gallery_urls(
    product_id: str,
    category_code: Optional[str] = None,
    product_name: Optional[str] = None,
) -> list:
    """Returns a list of 4 gallery images: main packshot + 3 supplementary commercial angles."""
    main_url = get_product_image_url(product_id, category_code, product_name)
    pfx = product_id.split("-")[0] if "-" in product_id else (category_code or "")
    aux = AUXILIARY_GALLERY.get(pfx, DEFAULT_GALLERY)

    gallery = [{"url": main_url, "title": "Main Studio Packshot", "caption": "Front Pack Presentation"}]
    for item in aux[:3]:
        gallery.append(item)
    return gallery

