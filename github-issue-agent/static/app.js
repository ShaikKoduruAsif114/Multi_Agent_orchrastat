document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const form = document.getElementById("agent-form");
    const tabIssue = document.getElementById("tab-issue");
    const tabSmart = document.getElementById("tab-smart");
    const groupIssueNumber = document.getElementById("group-issue-number");
    const groupProblemDesc = document.getElementById("group-problem-desc");
    const btnSubmit = document.getElementById("btn-submit-agent");
    const formSpinner = document.getElementById("form-spinner");
    const btnAuthBrowser = document.getElementById("btn-auth-browser");
    const authLabel = document.getElementById("auth-label");
    const terminalLogs = document.getElementById("terminal-logs");

    // Metrics
    const valLlmCalls = document.getElementById("val-llm-calls");
    const valRetryCount = document.getElementById("val-retry-count");
    const valTargetFiles = document.getElementById("val-target-files");

    // Modal Auth
    const modalAuth = document.getElementById("modal-auth");
    const modalInputToken = document.getElementById("modal-input-token");
    const btnSaveAuthToken = document.getElementById("btn-save-auth-token");
    const btnCancelAuth = document.getElementById("btn-cancel-auth");

    // Modal Approval
    const modalApproval = document.getElementById("modal-approval");
    const modalIssueTitle = document.getElementById("modal-issue-title");
    const modalFilesList = document.getElementById("modal-files-list");
    const modalProposedFix = document.getElementById("modal-proposed-fix");
    const modalTestsWritten = document.getElementById("modal-tests-written");
    const btnApproveFix = document.getElementById("btn-approve-fix");
    const btnRejectFix = document.getElementById("btn-reject-fix");
    const feedbackGroup = document.getElementById("feedback-group");
    const userFeedback = document.getElementById("user-feedback");

    // Modal Success
    const modalSuccess = document.getElementById("modal-success");
    const successPrUrl = document.getElementById("success-pr-url");
    const btnCloseSuccess = document.getElementById("btn-close-success");

    let currentMode = "issue";
    let pollInterval = null;

    // Check user session token on load
    function checkSessionAuth() {
        const savedToken = sessionStorage.getItem("user_github_token");
        if (savedToken) {
            authLabel.textContent = "Your GitHub Connected";
            document.querySelector("#github-auth-status .status-dot").className = "status-dot green";
        } else {
            authLabel.textContent = "Click to Connect Your GitHub";
            document.querySelector("#github-auth-status .status-dot").className = "status-dot amber";
        }
    }
    checkSessionAuth();

    // Mode Toggle Logic
    tabIssue.addEventListener("click", () => setMode("issue"));
    tabSmart.addEventListener("click", () => setMode("smart"));

    function setMode(mode) {
        currentMode = mode;
        if (mode === "issue") {
            tabIssue.classList.add("active");
            tabSmart.classList.remove("active");
            groupIssueNumber.classList.remove("hidden");
            groupProblemDesc.classList.add("hidden");
        } else {
            tabSmart.classList.add("active");
            tabIssue.classList.remove("active");
            groupIssueNumber.classList.add("hidden");
            groupProblemDesc.classList.remove("hidden");
        }
    }

    // Open Connect GitHub Modal
    btnAuthBrowser.addEventListener("click", (e) => {
        e.preventDefault();
        modalInputToken.value = sessionStorage.getItem("user_github_token") || "";
        modalAuth.classList.remove("hidden");
    });


    btnCancelAuth.addEventListener("click", () => {
        modalAuth.classList.add("hidden");
    });

    btnSaveAuthToken.addEventListener("click", () => {
        const token = modalInputToken.value.trim();
        if (token) {
            sessionStorage.setItem("user_github_token", token);
            logTerminal("✅ Successfully connected YOUR GitHub token to this session!", "sys");
        } else {
            sessionStorage.removeItem("user_github_token");
            logTerminal("Cleared session GitHub token.", "info");
        }
        checkSessionAuth();
        modalAuth.classList.add("hidden");
    });

    // Submit Agent Execution Form
    form.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const repoUrl = document.getElementById("repo_url").value.trim();
        const issueNumber = parseInt(document.getElementById("issue_number") ? document.getElementById("issue_number").value : "0") || 0;
        const problemDescription = document.getElementById("problem_description") ? document.getElementById("problem_description").value.trim() : "";
        const tokenOverrideInput = document.getElementById("token_override");
        const tokenOverride = tokenOverrideInput ? tokenOverrideInput.value.trim() : "";

        // Priority: Form Override Token > Session Storage Token
        const activeToken = tokenOverride || sessionStorage.getItem("user_github_token") || "";



        if (!activeToken) {
            logTerminal("⚠️ WARNING: No GitHub token set! Click 'Connect GitHub Popup' so PRs open under YOUR account.", "err");
        }

        logTerminal(`Launching Agent for ${repoUrl} [Mode: ${currentMode.toUpperCase()}]...`, "sys");
        setLoading(true);

        try {
            const res = await fetch("/api/run", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    repo_url: repoUrl,
                    mode: currentMode,
                    issue_number: issueNumber,
                    problem_description: problemDescription,
                    token: activeToken
                })
            });

            const data = await res.json();

            if (res.ok) {
                logTerminal("Agent workflow started. Tracking live execution state...", "info");
                startPollingStatus();
            } else {
                logTerminal(`Error: ${data.detail}`, "err");
                setLoading(false);
            }
        } catch (err) {
            logTerminal(`Failed to start workflow: ${err}`, "err");
            setLoading(false);
        }
    });

    // Poll Workflow Status from Backend
    function startPollingStatus() {
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(pollStatus, 1500);
    }

    async function pollStatus() {
        try {
            const res = await fetch("/api/status");
            const data = await res.json();

            // Update Metrics
            valLlmCalls.textContent = data.llm_calls || 0;
            valRetryCount.textContent = `${data.retry_count || 0} / 3`;
            valTargetFiles.textContent = (data.relevant_files || []).length;

            // Highlight Active Nodes
            updateNodeVisualizers(data.status);

            // Handle States
            if (data.status === "waiting_approval") {
                showApprovalModal(data);
            } else if ((data.status === "completed" || data.status === "finished") && data.pr_url) {
                clearInterval(pollInterval);
                setLoading(false);
                modalApproval.classList.add("hidden");
                showSuccessModal(data.pr_url);
            } else if (data.status === "completed" || data.status === "finished" || data.status === "failed") {
                clearInterval(pollInterval);
                setLoading(false);
                modalApproval.classList.add("hidden");
                if (data.errors && data.errors.length > 0) {
                    logTerminal(`⚠️ Workflow finished: ${data.errors.join("; ")}`, "err");
                } else {
                    logTerminal("Workflow execution finished.", "info");
                }
            }

        } catch (err) {
            console.error("Poll status error:", err);
        }
    }

    function updateNodeVisualizers(status) {
        document.querySelectorAll(".pipe-node").forEach(el => el.className = "pipe-node");

        if (status === "running") {
            document.getElementById("node-input_node").classList.add("completed");
            document.getElementById("node-fetch_node").classList.add("completed");
            document.getElementById("node-research_node").classList.add("completed");
            document.getElementById("node-code_writer_node").classList.add("running");
            document.getElementById("node-test_writer_node").classList.add("running");
        } else if (status === "waiting_approval") {
            document.querySelectorAll(".pipe-node").forEach(el => el.classList.add("completed"));
            document.getElementById("node-human_approval_node").classList.add("waiting");
        } else if (status === "completed") {
            document.querySelectorAll(".pipe-node").forEach(el => el.classList.add("completed"));
        }
    }

    // Modal Approval Logic
    function showApprovalModal(data) {
        modalIssueTitle.textContent = data.issue_title || "Code Fix Review";
        modalFilesList.textContent = `Target Files: ${(data.relevant_files || []).join(", ")}`;
        modalProposedFix.textContent = data.proposed_fix || "// Code fix generated by Llama 3.2";
        modalTestsWritten.textContent = data.tests_written || "// Pytest unit tests generated by Llama 3.2";
        modalApproval.classList.remove("hidden");
    }

    btnApproveFix.addEventListener("click", async () => {
        logTerminal("User Approved Fix! Proceeding to PR Creation on User's GitHub...", "sys");
        modalApproval.classList.add("hidden");
        await submitApprovalDecision(true, "");
    });

    btnRejectFix.addEventListener("click", async () => {
        if (feedbackGroup.classList.contains("hidden")) {
            feedbackGroup.classList.remove("hidden");
            userFeedback.focus();
            return;
        }

        const feedbackText = userFeedback.value.trim();
        logTerminal(`User Rejected Fix. Submitting feedback for retry: "${feedbackText}"`, "err");
        modalApproval.classList.add("hidden");
        feedbackGroup.classList.add("hidden");
        userFeedback.value = "";
        await submitApprovalDecision(false, feedbackText);
    });

    async function submitApprovalDecision(approved, feedback) {
        try {
            await fetch("/api/approval", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ approved, feedback })
            });
        } catch (err) {
            logTerminal(`Error submitting approval: ${err}`, "err");
        }
    }

    function showSuccessModal(url) {
        successPrUrl.href = url;
        successPrUrl.innerHTML = `<span>View Pull Request on GitHub ↗</span>`;
        modalSuccess.classList.remove("hidden");
        logTerminal(`✅ SUCCESS! Pull Request Created on YOUR GitHub: ${url}`, "sys");
    }


    btnCloseSuccess.addEventListener("click", () => {
        modalSuccess.classList.add("hidden");
    });

    function setLoading(isLoading) {
        if (isLoading) {
            btnSubmit.disabled = true;
            formSpinner.classList.remove("hidden");
        } else {
            btnSubmit.disabled = false;
            formSpinner.classList.add("hidden");
        }
    }

    function logTerminal(text, type = "info") {
        const line = document.createElement("div");
        line.className = `log-line ${type}`;
        const time = new Date().toLocaleTimeString();
        line.textContent = `[${time}] ${text}`;
        terminalLogs.appendChild(line);
        terminalLogs.scrollTop = terminalLogs.scrollHeight;
    }

    // Auto-start polling on page load to detect running/waiting approval workflows
    startPollingStatus();
});

