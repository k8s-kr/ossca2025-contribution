#!/bin/bash
if [ -z "$GITHUB_TOKEN" ]; then
  echo "Error: GITHUB_TOKEN environment variable not set."
  exit 1
fi
if [ $# -ne 2 ]; then
  echo "Usage: $0 <start-date YYYY-MM-DD> <end-date YYYY-MM-DD>"
  exit 1
fi
START="$1"
END="$2"
SINCE="${START}T00:00:00Z"
UNTIL="${END}T23:59:59Z"
LIMIT=150
USERS=(
  hyorimlee jongwooo NOHHYEONGJUN developowl eundms
  wonyongg wooneojun ianychoi kamothi S0okJu
  daeun-ops Antraxmin ppiyakk2
)
OWNER="kubernetes"
REPO="website"
API_COMMENTS="https://api.github.com/repos/$OWNER/$REPO/issues/comments"
PER_PAGE=100

declare -A issue_created_counts
declare -A issue_assigned_counts
declare -A pr_created_counts
declare -A pr_assigned_counts
declare -A comment_counts

echo "Checking GitHub activity from $START to $END"
echo

for user in "${USERS[@]}"
do
  echo "===== User: $user ====="


  # Issues created
  issues_output=$(gh issue list --repo $OWNER/$REPO --author "$user" --search "created:$START..$END" --state all --limit $LIMIT --json number,title,state,createdAt --template '{{range .}}{{printf "#%.0f %s %s %s\n" .number .title .state .createdAt}}{{end}}')
  issue_created_counts[$user]=$(echo "$issues_output" | grep -c '^#')
  echo "- Issues created:"${issue_created_counts[$user]}
  echo "$issues_output"

  # Issues assigned
  issues_output=$(gh issue list --repo $OWNER/$REPO --assignee "$user" --search "created:$START..$END" --state all --limit $LIMIT --json number,title,state,createdAt --template '{{range .}}{{printf "#%.0f %s %s %s\n" .number .title .state .createdAt}}{{end}}')
  issue_assigned_counts[$user]=$(echo "$issues_output" | grep -c '^#')
  echo "- Issues assigned:"${issue_assigned_counts[$user]}
  echo "$issues_output"

  # PRs created
  prs_output=$(gh pr list --repo $OWNER/$REPO --author "$user" --search "created:$START..$END" --state all --limit $LIMIT --json number,title,state,createdAt --template '{{range .}}{{printf "#%.0f %s %s %s\n" .number .title .state .createdAt}}{{end}}')
  pr_created_counts[$user]=$(echo "$prs_output" | grep -c '^#')
  echo "- PRs created:"${pr_created_counts[$user]}
  echo "$prs_output"
  
  # PRs created
  prs_output=$(gh pr list --repo $OWNER/$REPO --assignee "$user" --search "created:$START..$END" --state all --limit $LIMIT --json number,title,state,createdAt --template '{{range .}}{{printf "#%.0f %s %s %s\n" .number .title .state .createdAt}}{{end}}')
  pr_assigned_counts[$user]=$(echo "$prs_output" | grep -c '^#')
  echo "- PRs assigned:"${pr_assigned_counts[$user]}
  echo "$prs_output"

  # Comments Count (paginated)
  count=0
  page=1
  while : ; do
    response=$(curl -s -H "Authorization: Bearer $GITHUB_TOKEN" \
      "$API_COMMENTS?since=$SINCE&per_page=$PER_PAGE&page=$page")
    page_count=$(echo "$response" | jq --arg user "$user" --arg since "$SINCE" --arg until "$UNTIL" '
      [ .[] | select(.user.login==$user and (.created_at >= $since and .created_at <= $until)) ] | length
    ')
    count=$((count + page_count))
    length=$(echo "$response" | jq 'length')
    if [ "$length" -lt "$PER_PAGE" ]; then
      break
    fi
    page=$((page + 1))
  done
  comment_counts[$user]=$count
  echo "- Comments count: ${comment_counts[$user]}"
  echo
done

# Summary Table Print
echo "=== Summary Table ==="
echo "| User        | Issues Created | Issues Assigned | PRs Created | PRs Assigned | Comments Count |"
echo "|-------------|----------------|-----------------|-------------|--------------|----------------|"

for user in "${USERS[@]}"
do
  printf "| %-11s | %-14d | %-15d | %-11d | %-12d | %-14d |\n" \
    "$user" \
    "${issue_created_counts[$user]:-0}" \
    "${issue_assigned_counts[$user]:-0}" \
    "${pr_created_counts[$user]:-0}" \
    "${pr_assigned_counts[$user]:-0}" \
    "${comment_counts[$user]:-0}"
done

