export function requestsMapLabels(question:string) {
  // Compound acquisition/comparison belongs to the agent, not an old map's local labels.
  if(/\b(?:fetch|bring|compare|comparison|versus|find|create|generate|provide|retrieve|busiest|peak|years?)\b/i.test(question) || /\bshow\b.*\band\b/i.test(question))return false;
  if(/\b(?:don't|do not|without)\s+(?:add\s+)?label/i.test(question))return false;
  if(/^(?:please\s+)?(?:label|annotate)\s+(?:this|it|the selection)[.?!]?$/i.test(question.trim()))return true;
  return /\b(?:label(?:s|ings?|led)?|annotate|mark|pin(?:s)?)\b/i.test(question) &&
    /\b(?:map|heat\s?map|places?|points?|locations?|hot\s?spots?|detections?|thermal readings?)\b/i.test(question) &&
    /\b(?:can|could|please|add|put|place|draw|label|annotate|mark|pin)\b/i.test(question) &&
    !/\b(?:web|online|internet|search|look up|(?:find|show me)\s+(?:papers|studies|articles|sources|references))\b/i.test(question);
}

export function noteText(question:string) {
  const match=/^(?:please\s+)?(?:(?:can|could) you\s+)?(?:add|create|put|write)\s+(?:a\s+)?(?:sticky\s+)?note(?:\s+(?:saying|that says|with text)|\s*:)\s*(.+)$/is.exec(question.trim());
  return match?.[1].trim().replace(/^["“]|["”]$/g,'').slice(0,600) || '';
}

export function labelText(question:string) {
  const match=/^(?:please\s+)?(?:(?:can|could) you\s+)?label\s+(?:this|it|the selection|the selected (?:object|item|figure|shape))\s+(?:as\s+|with\s+)?(["“])(.+?)["”][.?!]?$/is.exec(question.trim());
  return match?.[2].trim().slice(0,120) || '';
}
