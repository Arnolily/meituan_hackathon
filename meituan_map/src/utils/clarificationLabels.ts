export function optionLabel(value: string) {
  if (value === "low") return "节省一些";
  if (value === "medium") return "价格适中";
  if (value === "high") return "品质优先";
  if (value === "do_not_care") return "不特别限制";
  const labels: Record<string, string> = {
    Chinese: "中餐",
    Japanese: "日料",
    Italian: "意餐",
    Mexican: "墨西哥菜",
    "American (New)": "新式美餐",
    "American (Traditional)": "传统美餐",
    Seafood: "海鲜",
    Thai: "泰餐",
    Indian: "印度菜",
    Korean: "韩餐",
    Vietnamese: "越南菜",
    Restaurants: "餐厅",
    Food: "餐饮",
    "Breakfast & Brunch": "早午餐",
    "Coffee & Tea": "咖啡或茶饮",
    Cafes: "咖啡馆",
    Museums: "博物馆",
    "Art Museums": "艺术博物馆",
    "Art Galleries": "画廊或艺术空间",
    Parks: "公园",
    "Shopping Centers": "购物中心",
    "Arts & Entertainment": "文化娱乐空间",
    Arcades: "游戏厅",
    "Active Life": "户外活动",
    Bars: "酒吧",
    "Beer Gardens": "啤酒花园",
    "Beer Bar": "啤酒吧",
    "Cocktail Bars": "鸡尾酒吧",
    Vegetarian: "素食",
    Vegan: "纯素",
    Tacos: "塔可",
    Bakeries: "烘焙店",
    Desserts: "甜品",
    "Juice Bars & Smoothies": "果汁和冰沙",
    "Ice Cream & Frozen Yogurt": "冰淇淋和冻酸奶",
  };
  return labels[value] ?? value.replace(/ & /g, "和");
}

export function questionLabel(question: string, field?: string, eventIndex?: number) {
  const segment = eventIndex ? `第 ${eventIndex} 段 · ` : "";
  if (field === "budget_level") return `${segment}预算范围`;
  if (field === "cuisine_category") {
    return `${segment}${question.includes("food") || question.includes("餐饮") ? "餐饮类型" : "地点类型"}`;
  }
  const cleaned = question
    .replace("Budget preference for", "预算偏好")
    .replace("What kind of food for", "餐饮类型")
    .replace("What kind of POI for", "地点类型")
    .replace("?", "");
  return cleaned
    .replace("Meal", "用餐")
    .replace("Coffee", "咖啡")
    .replace("Dinner", "晚餐")
    .replace("Lunch", "午餐")
    .replace("Park", "公园")
    .replace("Museum", "博物馆")
    .replace("Art", "艺术空间")
    .replace("Shopping", "购物")
    .replace("Activity", "活动")
    .replace("event_", "第 ")
    .replace(/(\d+)$/, "$1 段");
}
