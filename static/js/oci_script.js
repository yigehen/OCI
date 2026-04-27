document.addEventListener('DOMContentLoaded', function() {

    const profileList = document.getElementById('profileList');

    const currentProfileStatus = document.getElementById('currentProfileStatus');
    const profilesModalCurrentStatus = document.getElementById('profilesModalCurrentStatus');
    const connectedProfileEmptyState = document.getElementById('connectedProfileEmptyState');
    const connectedProfileDetails = document.getElementById('connectedProfileDetails');
    const connectedProfileAlias = document.getElementById('connectedProfileAlias');
    const connectedProfileUser = document.getElementById('connectedProfileUser');
    const connectedProfileRegion = document.getElementById('connectedProfileRegion');
    const connectedProfileProxy = document.getElementById('connectedProfileProxy');
    const connectedProfileTenancy = document.getElementById('connectedProfileTenancy');
    const connectedProfileRegDate = document.getElementById('connectedProfileRegDate');
    const connectedProfileSsh = document.getElementById('connectedProfileSsh');
    const connectedProfileFingerprint = document.getElementById('connectedProfileFingerprint');
    const connectedProfileMeta = document.getElementById('connectedProfileMeta');
    const connectedProfileStatusBadge = document.getElementById('connectedProfileStatusBadge');
    const profilesStatValue = document.getElementById('profilesStatValue');
    const profilesStatSub = document.getElementById('profilesStatSub');
    const snatchStatValue = document.getElementById('snatchStatValue');
    const snatchStatSub = document.getElementById('snatchStatSub');
    const networkStatValue = document.getElementById('networkStatValue');
    const networkStatSub = document.getElementById('networkStatSub');

    const sortAccountByDateHeader = document.getElementById('sortAccountByDate');
    const sortIcon = document.getElementById('sortIcon');
    const sortAccountByAliasHeader = document.getElementById('sortAccountByAlias');
    const sortAliasIcon = document.getElementById('sortAliasIcon');

    const addAccountModal = new bootstrap.Modal(document.getElementById('addAccountModal'));
    const profilesHubModalEl = document.getElementById('profilesHubModal');

    // 刷新添加账户窗口中的全局公钥状态文字
    async function loadAndDisplayDefaultKey() {
        const statusText = document.getElementById('defaultSshKeyStatusText');
        if (!statusText) return;
        try {
            const response = await apiRequest('/oci/api/default-ssh-key');
            if (response.key) {
                statusText.innerHTML = '<span class="text-success"><i class="bi bi-check-circle"></i> 已配置全局默认公钥</span>';
            } else {
                statusText.innerHTML = '<span class="text-warning"><i class="bi bi-exclamation-triangle"></i> 未配置全局默认公钥</span>';
            }
        } catch (e) {
            statusText.innerHTML = '<span class="text-danger">检查默认公钥失败</span>';
        }
    }

    // --- 全局默认 SSH 公钥设置逻辑 (从网络与配置 Hub 打开) ---
    const globalSshKeyModalEl = document.getElementById('globalSshKeyModal');
    let globalSshKeyModal = null;
    if (globalSshKeyModalEl) {
        globalSshKeyModal = new bootstrap.Modal(globalSshKeyModalEl);
    }

    const globalSshKeyHubBtn = document.getElementById('globalSshKeyHubBtn');
    const globalSshKeyInput = document.getElementById('globalSshKeyInput');
    const globalSshKeyFileInput = document.getElementById('globalSshKeyFileInput');
    const submitGlobalSshKeyBtn = document.getElementById('submitGlobalSshKeyBtn');

    // 1. 点击 Hub 按钮时拉取当前公钥并打开弹窗
    if (globalSshKeyHubBtn) {
        globalSshKeyHubBtn.addEventListener('click', async () => {
            if (typeof networkConfigHubModal !== 'undefined') {
                const hubModalInstance = bootstrap.Modal.getInstance(document.getElementById('networkConfigHubModal'));
                if (hubModalInstance) hubModalInstance.hide();
            }
            
            if (globalSshKeyInput) globalSshKeyInput.value = '正在拉取当前保存的公钥...';
            
            try {
                const response = await apiRequest('/oci/api/default-ssh-key');
                if (globalSshKeyInput) globalSshKeyInput.value = response.key || '';
            } catch (error) {
                if (globalSshKeyInput) globalSshKeyInput.value = '';
            }
            
            // 清空文件选择器
            if (globalSshKeyFileInput) globalSshKeyFileInput.value = '';
            setTimeout(() => { if (globalSshKeyModal) globalSshKeyModal.show(); }, 200);
        });
    }

    // 2. 选择文件后自动读取内容至 Textarea
    if (globalSshKeyFileInput) {
        globalSshKeyFileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = (event) => {
                if (globalSshKeyInput) {
                    globalSshKeyInput.value = event.target.result;
                    addLog('公钥文件读取成功，已填充至输入框', 'success');
                }
            };
            reader.onerror = () => addLog('读取公钥文件失败', 'error');
            reader.readAsText(file);
        });
    }

    // 3. 提交并保存公钥
    if (submitGlobalSshKeyBtn) {
        submitGlobalSshKeyBtn.addEventListener('click', async () => {
            const keyContent = globalSshKeyInput?.value.trim() || '';
            
            submitGlobalSshKeyBtn.disabled = true;
            const spinner = submitGlobalSshKeyBtn.querySelector('.spinner-border');
            if (spinner) spinner.classList.remove('d-none');

            try {
                const response = await apiRequest('/oci/api/default-ssh-key', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ key: keyContent })
                });
                
                addLog(response.message || '全局默认 SSH 公钥保存成功', 'success');
                if (globalSshKeyModal) globalSshKeyModal.hide();
                
                // 刷新添加账户页面的状态徽章
                loadAndDisplayDefaultKey(); 
            } catch (error) {
                // error 会被 apiRequest 的 catch 自动 log
            } finally {
                submitGlobalSshKeyBtn.disabled = false;
                if (spinner) spinner.classList.add('d-none');
            }
        });
    }
    // -----------------------------------------------------------

    document.getElementById('addAccountModal').addEventListener('shown.bs.modal', loadAndDisplayDefaultKey);
    profilesHubModalEl?.addEventListener('show.bs.modal', () => {
        loadProfiles();
    });

    const addNewProfileBtnModal = document.getElementById('addNewProfileBtnModal');
    const newProfileAlias = document.getElementById('newProfileAlias');
    const newProfileConfigText = document.getElementById('newProfileConfigText');
    const newProfileKeyFile = document.getElementById('newProfileKeyFile');

    const refreshInstancesBtn = document.getElementById('refreshInstancesBtn');
    const createInstanceBtn = document.getElementById('createInstanceBtn');
    const networkSettingsBtn = document.getElementById('networkSettingsBtn');
    const instanceList = document.getElementById('instanceList');
    const logOutput = document.getElementById('logOutput');
    const clearLogBtn = document.getElementById('clearLogBtn');

    const snatchLogOutput = document.getElementById('snatchLogOutput');
    const clearSnatchLogBtn = document.getElementById('clearSnatchLogBtn');
    const snatchLogArea = document.getElementById('snatchLogArea');

    const launchInstanceModal = new bootstrap.Modal(document.getElementById('createLaunchInstanceModal'));
    const launchInstanceModalEl = document.getElementById('createLaunchInstanceModal');
    const viewSnatchTasksModal = new bootstrap.Modal(document.getElementById('viewSnatchTasksModal'));
    const viewSnatchTasksModalEl = document.getElementById('viewSnatchTasksModal');
    const taskResultModal = new bootstrap.Modal(document.getElementById('taskResultModal'));
    const networkSettingsModal = new bootstrap.Modal(document.getElementById('networkSettingsModal'));
    const networkConfigHubModal = new bootstrap.Modal(document.getElementById('networkConfigHubModal'));
    const editInstanceModal = new bootstrap.Modal(document.getElementById('editInstanceModal'));
    const confirmActionModal = new bootstrap.Modal(document.getElementById('confirmActionModal'));
    const cloudflareSettingsModal = new bootstrap.Modal(document.getElementById('cloudflareSettingsModal'));
    const tgSettingsModal = new bootstrap.Modal(document.getElementById('tgSettingsModal'));

    const disconnectAccountBtn = document.getElementById('disconnectAccountBtn');

    if (disconnectAccountBtn) {
        disconnectAccountBtn.addEventListener('click', async () => {
            try {
                await apiRequest('/oci/api/session', { method: 'DELETE' });
                addLog('已成功断开连接', 'success');
                await checkSession(false);
            } catch (e) {
                addLog('断开连接失败: ' + e.message, 'error');
            }
        });
    }

    const instanceCountInput = document.getElementById('instanceCount');
    const launchInstanceShapeSelect = document.getElementById('instanceShape');
    const launchFlexConfig = document.getElementById('flexShapeConfig');
    const submitLaunchInstanceBtn = document.getElementById('submitLaunchInstanceBtn');

    const instancePasswordInput = document.getElementById('instancePassword');
    const enablePasswordLoginCheck = document.getElementById('enablePasswordLoginCheck');
    const passwordInputContainer = document.getElementById('passwordInputContainer');

    const sshKeySourceRadios = document.getElementsByName('sshKeySource');
    const customSshKeyContainer = document.getElementById('customSshKeyContainer');
    const launchCustomSshKey = document.getElementById('launchCustomSshKey');

    const stopSnatchTaskBtn = document.getElementById('stopSnatchTaskBtn');
    const resumeSnatchTaskBtn = document.getElementById('resumeSnatchTaskBtn');
    const deleteSnatchTaskBtn = document.getElementById('deleteSnatchTaskBtn');
    const deleteCompletedBtn = document.getElementById('deleteCompletedBtn');

    const runningSnatchTasksList = document.getElementById('runningSnatchTasksList');
    const completedSnatchTasksList = document.getElementById('completedSnatchTasksList');
    const actionAreaProfile = document.getElementById('actionAreaProfile');
    const ingressRulesTable = document.getElementById('ingressRulesTable');
    const egressRulesTable = document.getElementById('egressRulesTable');

    const vcnSelect = document.getElementById('vcnSelect');
    const securityListSelect = document.getElementById('securityListSelect');
    const networkRulesSpinner = document.getElementById('networkRulesSpinner');

    const addIngressRuleBtn = document.getElementById('addIngressRuleBtn');
    const addEgressRuleBtn = document.getElementById('addEgressRuleBtn');
    const saveNetworkRulesBtn = document.getElementById('saveNetworkRulesBtn');
    const openFirewallBtn = document.getElementById('openFirewallBtn');

    const editDisplayName = document.getElementById('editDisplayName');
    const saveDisplayNameBtn = document.getElementById('saveDisplayNameBtn');
    const editFlexInstanceConfig = document.getElementById('editFlexInstanceConfig');
    const editOcpus = document.getElementById('editOcpus');
    const editMemory = document.getElementById('editMemory');
    const saveFlexConfigBtn = document.getElementById('saveFlexConfigBtn');
    const editBootVolumeSize = document.getElementById('editBootVolumeSize');
    const saveBootVolumeSizeBtn = document.getElementById('saveBootVolumeSizeBtn');
    const editVpus = document.getElementById('editVpus');
    const saveVpusBtn = document.getElementById('saveVpusBtn');
    const editInstanceIpList = document.getElementById('editInstanceIpList');
    const editInstanceIpv6List = document.getElementById('editInstanceIpv6List');

    const confirmActionModalLabel = document.getElementById('confirmActionModalLabel');
    const confirmActionModalBody = document.getElementById('confirmActionModalBody');
    const confirmActionModalTerminateOptions = document.getElementById('confirmActionModalTerminateOptions');
    const confirmDeleteVolumeCheck = document.getElementById('confirmDeleteVolumeCheck');
    const confirmActionModalConfirmBtn = document.getElementById('confirmActionModalConfirmBtn');

    const tgBotTokenInput = document.getElementById('tgBotToken');
    const tgChatIdInput = document.getElementById('tgChatId');
    const saveTgConfigBtn = document.getElementById('saveTgConfigBtn');
    const getApiKeyBtn = document.getElementById('getApiKeyBtn');
    const apiKeyInput = document.getElementById('apiKeyInput');

    const cloudflareApiTokenInput = document.getElementById('cloudflareApiToken');
    const cloudflareZoneIdInput = document.getElementById('cloudflareZoneId');
    const cloudflareDomainInput = document.getElementById('cloudflareDomain');
    const saveCloudflareConfigBtn = document.getElementById('saveCloudflareConfigBtn');
    const autoBindDomainCheck = document.getElementById('autoBindDomainCheck');

    const xuiManagerUrlInput = document.getElementById('xuiManagerUrl');
    const xuiManagerSecretInput = document.getElementById('xuiManagerSecret');
    const saveXuiConfigBtn = document.getElementById('saveXuiConfigBtn');

    const instanceActionButtons = {
        start: document.getElementById('startBtn'),
        stop: document.getElementById('stopBtn'),
        restart: document.getElementById('restartBtn'),
        editInstance: document.getElementById('editInstanceBtn'),
        changeIp: document.getElementById('changeIpBtn'),
        addIp: document.getElementById('addIpBtn'),
        assignIpv6: document.getElementById('assignIpv6Btn'),
        terminate: document.getElementById('terminateBtn'),
    };

    let currentInstances = [];
    let selectedInstance = null;
    let currentSecurityList = null;

    let globalCfStatus = null;
    let globalTgStatus = null;
    let globalSshStatus = null;

    const accountColors = {};
    const colorPalette = ['#007bff', '#28a745', '#dc3545', '#ffc107', '#17a2b8', '#6610f2', '#e83e8c'];
    let colorIndex = 0;
    const snatchTaskAnnounced = {};

    function getAccountColor(alias) {
        if (!accountColors[alias]) {
            accountColors[alias] = colorPalette[colorIndex % colorPalette.length];
            colorIndex++;
        }
        return accountColors[alias];
    }

    launchInstanceShapeSelect.addEventListener('change', () => {
        const isFlex = launchInstanceShapeSelect.value.includes('Flex');
        launchFlexConfig.style.display = isFlex ? 'flex' : 'none';
    });
    launchInstanceShapeSelect.dispatchEvent(new Event('change'));

    sshKeySourceRadios.forEach(radio => {
        radio.addEventListener('change', (e) => {
            if (e.target.value === 'custom') {
                customSshKeyContainer.classList.remove('d-none');
            } else {
                customSshKeyContainer.classList.add('d-none');
            }
        });
    });

    if (enablePasswordLoginCheck && passwordInputContainer) {
        enablePasswordLoginCheck.addEventListener('change', function() {
            if (this.checked) {
                passwordInputContainer.classList.remove('d-none');
            } else {
                passwordInputContainer.classList.add('d-none');
                instancePasswordInput.value = '';
            }
        });
    }

    launchInstanceModalEl.addEventListener('show.bs.modal', async () => {
        if (enablePasswordLoginCheck) {
            enablePasswordLoginCheck.checked = false;
            enablePasswordLoginCheck.dispatchEvent(new Event('change'));
        }
        document.getElementById('sshKeySourceDefault').checked = true;
        customSshKeyContainer.classList.add('d-none');
        launchCustomSshKey.value = '';

        const defaultScriptInput = document.getElementById('defaultStartupScriptInput');
        const editBtn = document.getElementById('editDefaultScriptBtn');
        const extraScriptInput = document.getElementById('startupScript');

        if (defaultScriptInput) {
            defaultScriptInput.readOnly = true;
            defaultScriptInput.value = "正在从服务器同步默认脚本...";

            if (editBtn) {
                editBtn.innerHTML = '<i class="bi bi-pencil-square"></i> 编辑';
                editBtn.classList.remove('btn-outline-success');
                editBtn.classList.add('btn-outline-secondary');
            }

            try {
                const response = await apiRequest('/oci/api/default-script');
                defaultScriptInput.value = response.script || "";
            } catch (error) {
                console.error("加载默认脚本失败", error);
                defaultScriptInput.value = "";
            }
        }

        if (extraScriptInput) {
            extraScriptInput.value = '';
        }

        if (editBtn) {
            editBtn.onclick = async () => {
                const isReadOnly = defaultScriptInput.readOnly;

                if (isReadOnly) {
                    defaultScriptInput.readOnly = false;
                    defaultScriptInput.focus();
                    editBtn.innerHTML = '<i class="bi bi-check-lg"></i> 保存';
                    editBtn.classList.replace('btn-outline-secondary', 'btn-outline-success');
                } else {
                    const currentVal = defaultScriptInput.value.trim();
                    editBtn.disabled = true;
                    editBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 保存中...';

                    try {
                        await apiRequest('/oci/api/default-script', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ script: currentVal })
                        });
                        addLog('默认开机脚本已成功保存至服务器文件！', 'success');
                    } catch (error) {
                        addLog('保存脚本失败: ' + error.message, 'error');
                    } finally {
                        editBtn.disabled = false;
                        defaultScriptInput.readOnly = true;
                        editBtn.innerHTML = '<i class="bi bi-pencil-square"></i> 编辑';
                        editBtn.classList.replace('btn-outline-success', 'btn-outline-secondary');
                    }
                }
            };
        }

        // 加载操作系统列表并动态获取实例规格
        loadAndDisplayOS();
    });

    // 监听操作系统选择变化，动态更新规格
    const instanceOSSelect = document.getElementById('instanceOS');
    if (instanceOSSelect) {
        instanceOSSelect.addEventListener('change', updateAvailableShapes);
    }

    submitLaunchInstanceBtn.addEventListener('click', () => {
        const proceedWithLaunch = async () => {
            const originalBtnText = submitLaunchInstanceBtn.innerHTML;
            submitLaunchInstanceBtn.disabled = true;
            submitLaunchInstanceBtn.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> 提交中...';

            const resetButton = () => {
                submitLaunchInstanceBtn.disabled = false;
                submitLaunchInstanceBtn.innerHTML = originalBtnText;
            };

            const shape = launchInstanceShapeSelect.value;
            if (!shape) {
                addLog('请选择一个有效的实例规格。', 'error');
                resetButton();
                return;
            }

            const isPasswordEnabled = enablePasswordLoginCheck && enablePasswordLoginCheck.checked;
            const passwordVal = isPasswordEnabled ? instancePasswordInput.value.trim() : "";

            let customSshKey = null;
            const selectedKeySource = document.querySelector('input[name="sshKeySource"]:checked').value;
            if (selectedKeySource === 'custom') {
                customSshKey = launchCustomSshKey.value.trim();
                if (!customSshKey) {
                    addLog('选择了自定义 SSH 公钥但内容为空！', 'error');
                    resetButton();
                    return;
                }
            }

            const defaultScriptVal = document.getElementById('defaultStartupScriptInput').value.trim();
            const extraScriptVal = document.getElementById('startupScript').value.trim();
            let finalStartupScript = defaultScriptVal;
            if (extraScriptVal) {
                finalStartupScript = defaultScriptVal + "\n" + extraScriptVal;
            }

            const details = {
                display_name_prefix: document.getElementById('instanceNamePrefix').value.trim(),
                instance_count: parseInt(instanceCountInput.value, 10),
                instance_password: passwordVal,
                enable_password_auth: isPasswordEnabled,
                custom_ssh_key: customSshKey,
                os_name_version: document.getElementById('instanceOS').value,
                shape: shape,
                boot_volume_size: parseInt(document.getElementById('bootVolumeSize').value, 10),
                startup_script: finalStartupScript,
                min_delay: parseInt(document.getElementById('minDelay').value, 10) || 30,
                max_delay: parseInt(document.getElementById('maxDelay').value, 10) || 90,
                auto_bind_domain: autoBindDomainCheck.checked
            };

            if (shape.includes('Flex')) {
                details.ocpus = parseInt(document.getElementById('instanceOcpus').value, 10);
                details.memory_in_gbs = parseInt(document.getElementById('instanceMemory').value, 10);
            }

            if (details.min_delay >= details.max_delay) {
                addLog('最短重试间隔必须小于最长重试间隔', 'error');
                resetButton();
                return;
            }
            if (!details.display_name_prefix) {
                addLog('实例名称/前缀不能为空', 'error');
                resetButton();
                return;
            }

            let logMessage = `正在提交抢占实例 [${details.display_name_prefix}] 的任务...`;
            if (details.auto_bind_domain) {
                logMessage += ' (已启用自动域名绑定)';
            }
            addLog(logMessage);

            try {
                const response = await apiRequest('/oci/api/launch-instance', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(details)
                });
                addLog(response.message, 'success');
                launchInstanceModal.hide();
                setTimeout(resetButton, 500);

                if (response.task_ids && Array.isArray(response.task_ids)) {
                    response.task_ids.forEach(pollTaskStatus);
                    // 提交任务后调用后台静默拉取
                    loadSnatchTasks();
                }
            } catch (error) {
                resetButton();
            }
        };

        const shape = launchInstanceShapeSelect.value;
        const requestedCount = parseInt(instanceCountInput.value, 10);
        const requestedBootVolumeSize = parseInt(document.getElementById('bootVolumeSize').value, 10);

        const activeInstances = currentInstances.filter(inst =>
            !['TERMINATED', 'TERMINATING'].includes(inst.lifecycle_state)
        );

        const newRequestedTotalSize = requestedCount * requestedBootVolumeSize;
        const currentTotalBootVolumeSize = activeInstances.reduce((total, inst) => {
            const sizeInGb = parseInt(inst.boot_volume_size_gb, 10);
            return total + (isNaN(sizeInGb) ? 0 : sizeInGb);
        }, 0);

        if ((currentTotalBootVolumeSize + newRequestedTotalSize) > 200) {
            confirmActionModalLabel.textContent = '警告: 超出免费额度';
            confirmActionModalBody.innerHTML = `您当前已使用 <strong>${currentTotalBootVolumeSize} GB</strong> 磁盘，本次请求将导致总量达到 <strong>${currentTotalBootVolumeSize + newRequestedTotalSize} GB</strong>，超出 200 GB 的免费额度。这可能会导致您的账户产生额外费用。<br><br>确定要继续吗？`;
            confirmActionModalConfirmBtn.onclick = () => {
                confirmActionModal.hide();
                proceedWithLaunch();
            };
            confirmActionModal.show();
            return;
        }

        if (shape === 'VM.Standard.E2.1.Micro') {
            const existingAMDCount = activeInstances.filter(inst => inst.shape === shape).length;
            if ((existingAMDCount + requestedCount) > 2) {
                addLog(`免费账户最多只能创建2个AMD实例，您已有 ${existingAMDCount} 个活动实例，无法再创建 ${requestedCount} 个。`, 'error');
                return;
            }
        }

        proceedWithLaunch();
    });

    const snatchTaskTabs = document.querySelectorAll('#snatchTaskTabs button[data-bs-toggle="tab"]');
    snatchTaskTabs.forEach(tab => {
        tab.addEventListener('shown.bs.tab', event => {
            const runningDeleteAction = document.getElementById('running-delete-action');
            if (event.target.id === 'running-tab') {
                document.getElementById('running-actions').style.display = 'flex';
                document.getElementById('completed-actions').style.display = 'none';
                runningDeleteAction.style.display = 'block';
                snatchLogArea.style.display = 'block';
            } else if (event.target.id === 'completed-tab') {
                document.getElementById('running-actions').style.display = 'none';
                document.getElementById('completed-actions').style.display = 'flex';
                runningDeleteAction.style.display = 'none';
                snatchLogArea.style.display = 'none';
            }
        });
    });

    viewSnatchTasksModalEl.addEventListener('shown.bs.modal', function () {
        snatchLogOutput.scrollTop = snatchLogOutput.scrollHeight;
    });

    document.getElementById('viewSnatchTasksBtn').addEventListener('click', function() {
        const runningTabBtn = document.getElementById('running-tab');
        const completedTabBtn = document.getElementById('completed-tab');
        const runningPane = document.getElementById('running-tab-pane');
        const completedPane = document.getElementById('completed-tab-pane');

        runningTabBtn.classList.add('active');
        completedTabBtn.classList.remove('active');
        runningPane.classList.add('show', 'active');
        completedPane.classList.remove('show', 'active');

        document.getElementById('running-actions').style.display = 'flex';
        document.getElementById('completed-actions').style.display = 'none';
        document.getElementById('running-delete-action').style.display = 'block';
        snatchLogArea.style.display = 'block';

        loadSnatchTasks();
    });

    // 动态加载操作系统
    async function loadAndDisplayOS() {
        const osSelect = document.getElementById('instanceOS');
        const shapeSelect = document.getElementById('instanceShape');

        if (!osSelect || !shapeSelect) return;

        osSelect.innerHTML = '<option value="">正在加载系统列表...</option>';
        osSelect.disabled = true;
        shapeSelect.innerHTML = '<option value="">等待选择系统...</option>';
        shapeSelect.disabled = true;
        submitLaunchInstanceBtn.disabled = true;

        try {
            const versions = await apiRequest('/oci/api/available-os-versions');
            osSelect.innerHTML = '';

            if (versions.length === 0) {
                osSelect.innerHTML = '<option value="">未找到任何支持的操作系统</option>';
            } else {
                versions.forEach(ver => {
                    const parts = ver.split('-');
                    const displayVer = parts.length > 1 ? `${parts[0]} ${parts[1]}` : ver;

                    const option = document.createElement('option');
                    option.value = ver;
                    option.textContent = displayVer;
                    osSelect.appendChild(option);
                });

                osSelect.disabled = false;
                osSelect.selectedIndex = 0;
                await updateAvailableShapes();
            }
        } catch (error) {
            osSelect.innerHTML = '<option value="">加载失败</option>';
            addLog('获取操作系统版本失败，请检查网络或账号权限。', 'error');
        } finally {
            osSelect.disabled = false;
        }
    }

    // 动态刷新可用规格
    async function updateAvailableShapes() {
        const osSelect = document.getElementById('instanceOS');
        const shapeSelect = document.getElementById('instanceShape');

        if (!osSelect || !shapeSelect) return;
        const os_name_version = osSelect.value;

        if (!os_name_version) return;

        shapeSelect.innerHTML = '<option value="">正在刷新实例规格...</option>';
        shapeSelect.disabled = true;
        submitLaunchInstanceBtn.disabled = true;

        try {
            const shapes = await apiRequest(`/oci/api/available-shapes?os_name_version=${os_name_version}`);
            shapeSelect.innerHTML = '';
            if (shapes.length === 0) {
                shapeSelect.innerHTML = '<option value="">当前系统无可用规格</option>';
            } else {
                shapes.sort((a, b) => {
                    const weightA = a.includes('A1.Flex') ? 2 : (a.includes('E2.1.Micro') ? 1 : 0);
                    const weightB = b.includes('A1.Flex') ? 2 : (b.includes('E2.1.Micro') ? 1 : 0);
                    if (weightA !== weightB) return weightB - weightA;
                    return a.localeCompare(b);
                });

                const seenShapes = new Set();
                shapes.forEach(shape => {
                    if (!seenShapes.has(shape)) {
                        seenShapes.add(shape);
                        const option = document.createElement('option');
                        option.value = shape;
                        
                        if (shape === 'VM.Standard.A1.Flex') {
                            option.textContent = '🌟 VM.Standard.A1.Flex (ARM 免费)';
                        } else if (shape === 'VM.Standard.E2.1.Micro') {
                            option.textContent = '🌟 VM.Standard.E2.1.Micro (AMD 免费)';
                        } else {
                            option.textContent = shape;
                        }
                        
                        shapeSelect.appendChild(option);
                    }
                });

                submitLaunchInstanceBtn.disabled = false;
            }
        } catch (error) {
            shapeSelect.innerHTML = '<option value="">获取规格失败</option>';
            addLog('自动刷新实例规格失败，请检查网络或账号权限。', 'error');
        } finally {
            shapeSelect.disabled = false;
            shapeSelect.dispatchEvent(new Event('change'));
        }
    }

    function addLog(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const typeMap = { 'error': 'text-danger', 'success': 'text-success', 'warning': 'text-warning' };
        const color = typeMap[type] || '';
        const logEntry = document.createElement('div');
        logEntry.className = color;
        logEntry.innerHTML = `[${timestamp}] ${message.replace(/\n/g, '<br>')}`;
        logOutput.appendChild(logEntry);
        logOutput.scrollTop = logOutput.scrollHeight;
    }

    function addSnatchLog(message, accountAlias) {
        const timestamp = new Date().toLocaleTimeString();
        const color = getAccountColor(accountAlias);

        const logEntry = document.createElement('div');
        logEntry.style.color = color;
        logEntry.innerHTML = `[${timestamp}] <strong style="color: ${color};">[${accountAlias || '未知账户'}]</strong> ${message.replace(/\n/g, '<br>')}`;

        snatchLogOutput.appendChild(logEntry);
        snatchLogOutput.scrollTop = snatchLogOutput.scrollHeight;
    }

    clearLogBtn.addEventListener('click', () => logOutput.innerHTML = '');
    clearSnatchLogBtn.addEventListener('click', () => snatchLogOutput.innerHTML = '');

    async function apiRequest(url, options = {}) {
        try {
            const response = await fetch(url, options);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ error: `HTTP 错误! 状态: ${response.status}` }));
                throw new Error(errorData.error || `HTTP 错误! 状态: ${response.status}`);
            }
            const text = await response.text();
            return text ? JSON.parse(text) : {};
        } catch (error) {
            addLog(`请求失败: ${error.message}`, 'error');
            throw error;
        }
    }

    // 独立控制操作按钮的状态
    function updateActionButtonsState() {
        if (!selectedInstance) {
            Object.values(instanceActionButtons).forEach(btn => btn.disabled = true);
            return;
        }
        const state = selectedInstance.lifecycle_state;
        const isTerminated = ['TERMINATED', 'TERMINATING'].includes(state);
        Object.values(instanceActionButtons).forEach(btn => btn.disabled = isTerminated);
        instanceActionButtons.start.disabled = state !== 'STOPPED';
        instanceActionButtons.stop.disabled = state !== 'RUNNING';
        instanceActionButtons.restart.disabled = state !== 'RUNNING';
        instanceActionButtons.changeIp.disabled = state !== 'RUNNING';
        instanceActionButtons.addIp.disabled = state !== 'RUNNING';
        instanceActionButtons.assignIpv6.disabled = !(state === 'RUNNING' && selectedInstance.vnic_id);
    }

    // ⭐ 修复点：支持静默刷新，不再粗暴覆盖 innerHTML 导致白屏闪烁 ⭐
    async function refreshInstances(isSilent = false) {
        const originalBtnHtml = refreshInstancesBtn.innerHTML;
        
        if (!isSilent) {
            addLog('正在刷新实例列表...');
            refreshInstancesBtn.disabled = true;
            refreshInstancesBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 刷新中...';
        }

        try {
            const instances = await apiRequest('/oci/api/instances');
            currentInstances = instances;
            
            // 记住当前选中的行 ID
            const selectedId = selectedInstance ? selectedInstance.id : null;
            
            instanceList.innerHTML = '';
            if (instances.length === 0) {
                instanceList.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-5">未找到任何实例</td></tr>`;
                selectedInstance = null;
            } else {
                instances.forEach(inst => {
                    const tr = document.createElement('tr');
                    tr.dataset.instanceId = inst.id;
                    tr.dataset.instanceData = JSON.stringify(inst);
                    const state = inst.lifecycle_state;
                    let dotClass = state === 'RUNNING' ? 'status-running' : (state === 'STOPPED' ? 'status-stopped' : 'status-other');
                    tr.innerHTML = `
                        <td class="align-middle" style="text-align: left; padding-left: 1rem;">${inst.display_name}</td>
                        <td class="text-center align-middle"><div class="status-cell justify-content-center d-flex"><span class="status-dot ${dotClass} me-2"></span><span>${state}</span></div></td>
                        <td class="text-center align-middle">${inst.public_ip || '无'}</td>
                        <td class="text-center align-middle">${inst.ipv6_address || '无'}</td>
                        <td class="text-center align-middle">${inst.ocpus}c / ${inst.memory_in_gbs}g / ${inst.boot_volume_size_gb}</td>
                        <td class="text-center align-middle">${new Date(inst.time_created).toLocaleString()}</td>`;
                    
                    // 恢复选中状态
                    if (inst.id === selectedId) {
                        tr.classList.add('table-active');
                        selectedInstance = inst;
                    }
                    instanceList.appendChild(tr);
                });
            }
            
            updateActionButtonsState();
            
            if (!isSilent) addLog('实例列表刷新成功!', 'success');
        } catch (error) {
            currentInstances = [];
            if (instanceList.children.length === 0 || !isSilent) {
                instanceList.innerHTML = `<tr><td colspan="6" class="text-center text-danger py-5">加载实例列表失败</td></tr>`;
            }
            selectedInstance = null;
            updateActionButtonsState();
        } finally {
            if (!isSilent) {
                refreshInstancesBtn.disabled = false;
                refreshInstancesBtn.innerHTML = originalBtnHtml;
            }
        }
    }

    refreshInstancesBtn.addEventListener('click', () => refreshInstances(false));

    function updateStatCards({ profileCount = null, currentAlias = null, runningCount = null, completedCount = null, cloudflareConfigured = null, tgConfigured = null, defaultKeyConfigured = null } = {}) {
        // 1. 账号管理卡片
        if (profilesStatValue) {
            profilesStatValue.textContent = profileCount !== null ? `${profileCount} Accounts` : 'OCI Profiles';
        }
        if (profilesStatSub) {
            if (currentAlias) {
                profilesStatSub.textContent = `当前连接: ${currentAlias}`;
            } else {
                profilesStatSub.textContent = '连接、排序、编辑、代理与配置管理';
            }
        }
        
        // 2. 抢占任务卡片
        if (snatchStatValue && (runningCount !== null || completedCount !== null)) {
            snatchStatValue.textContent = `${runningCount ?? 0} Running / ${completedCount ?? 0} Done`;
        }
        if (snatchStatSub && runningCount === null && completedCount === null) {
            snatchStatSub.textContent = '实时任务、日志、暂停恢复与删除';
        }

        // 3. 记录网络与配置卡片状态
        if (cloudflareConfigured !== null) globalCfStatus = cloudflareConfigured;
        if (tgConfigured !== null) globalTgStatus = tgConfigured;
        if (defaultKeyConfigured !== null) globalSshStatus = defaultKeyConfigured;

        // 4. 更新网络与配置卡片显示
        if (networkStatValue) {
            const ssh = globalSshStatus === null ? 'SSH 未知' : (globalSshStatus ? 'SSH 已配置' : 'SSH 未配置');
            const cf = globalCfStatus === null ? 'CF 未知' : (globalCfStatus ? 'CF 已配置' : 'CF 未配置');
            const tg = globalTgStatus === null ? 'TG 未知' : (globalTgStatus ? 'TG 已配置' : 'TG 未配置');
            networkStatValue.textContent = `${ssh} / ${cf} / ${tg}`;
        }
        if (networkStatSub) {
            networkStatSub.textContent = '统一管理全局公钥、安全规则与通知解析';
        }
    }

    async function refreshDashboardSummaries(currentAlias = null) {
        try {
            const [profiles, running, completed, cloudflareConfig, tgConfig, defaultKeyResponse] = await Promise.all([
                apiRequest('/oci/api/profiles'),
                apiRequest('/oci/api/tasks/snatching/running'),
                apiRequest('/oci/api/tasks/snatching/completed'),
                apiRequest('/oci/api/cloudflare-config'),
                apiRequest('/oci/api/tg-config'),
                apiRequest('/oci/api/default-ssh-key')
            ]);

            updateStatCards({
                profileCount: Array.isArray(profiles) ? profiles.length : 0,
                currentAlias,
                runningCount: Array.isArray(running) ? running.length : 0,
                completedCount: Array.isArray(completed) ? completed.length : 0,
                cloudflareConfigured: !!(cloudflareConfig && (cloudflareConfig.api_token || cloudflareConfig.zone_id || cloudflareConfig.domain)),
                tgConfigured: !!(tgConfig && (tgConfig.bot_token || tgConfig.chat_id)),
                defaultKeyConfigured: !!(defaultKeyResponse && defaultKeyResponse.key)
            });
        } catch (error) {
            console.warn('refreshDashboardSummaries failed:', error);
        }
    }

    async function renderConnectedProfileDetails(alias) {
        if (!connectedProfileDetails || !connectedProfileEmptyState || !alias) return;
        try {
            const profileData = await apiRequest(`/oci/api/profiles/${alias}`);
            connectedProfileAlias.textContent = alias;
            connectedProfileAlias.title = alias;

            let userText = profileData.user_display_name || profileData.user || '-';
            if (userText.startsWith('ocid1.')) userText = '-';

            if (connectedProfileUser) {
                connectedProfileUser.textContent = userText;
                connectedProfileUser.title = userText;
            }

            connectedProfileRegion.textContent = profileData.region || '未设置';
            connectedProfileRegion.title = profileData.region || '未设置';
            connectedProfileProxy.textContent = profileData.proxy || '未设置';
            connectedProfileProxy.title = profileData.proxy || '未设置';

            let tenancyText = profileData.tenancy_display_name || profileData.tenancy_name || profileData.tenancy || '-';
            if (tenancyText.startsWith('ocid1.')) tenancyText = '-';

            if (connectedProfileTenancy) {
                connectedProfileTenancy.textContent = tenancyText;
                connectedProfileTenancy.title = tenancyText;
            }

            connectedProfileRegDate.textContent = profileData.registration_date || '待同步';
            connectedProfileRegDate.title = profileData.registration_date || '待同步';
            connectedProfileSsh.innerHTML = profileData.default_ssh_public_key
                ? '<span class="badge bg-success-subtle text-success border border-success-subtle">已配置默认 SSH 公钥</span>'
                : '<span class="badge bg-secondary-subtle text-secondary border border-secondary-subtle">未配置默认 SSH 公钥</span>';
            if (connectedProfileStatusBadge) {
                connectedProfileStatusBadge.innerHTML = '<span class="badge bg-success-subtle text-success border border-success-subtle">已连接</span>';
            }
            if (connectedProfileFingerprint) {
                connectedProfileFingerprint.textContent = profileData.fingerprint || '未设置';
                connectedProfileFingerprint.title = profileData.fingerprint || '未设置';
            }
            if (connectedProfileMeta) {
                connectedProfileMeta.textContent = `租户ID: ${profileData.tenancy || 'N/A'} | 区域: ${profileData.region || 'N/A'} | 用户: ${profileData.user || 'N/A'}`;
                connectedProfileMeta.title = connectedProfileMeta.textContent;
            }

            if (tenancyText !== '-') localStorage.setItem('oci_tenancy_' + alias, tenancyText);
            if (userText !== '-') localStorage.setItem('oci_user_' + alias, userText);

            const rowTenancy = document.getElementById('row-tenancy-' + alias);
            const rowUser = document.getElementById('row-user-' + alias);
            if (rowTenancy) { rowTenancy.textContent = tenancyText; rowTenancy.title = tenancyText; }
            if (rowUser) { rowUser.textContent = userText; rowUser.title = userText; }

            connectedProfileEmptyState.classList.add('d-none');
            connectedProfileDetails.classList.remove('d-none');
        } catch (error) {
            connectedProfileEmptyState.innerHTML = '<div class="mb-2"><i class="bi bi-exclamation-triangle fs-2"></i></div><strong>当前账户详情加载失败，请稍后重试</strong>';
            connectedProfileEmptyState.classList.remove('d-none');
            connectedProfileDetails.classList.add('d-none');
        }
    }

    function resetConnectedProfileDetails(message = '请先在"OCI Profiles"弹出窗口中选择并连接一个账号') {
        if (!connectedProfileDetails || !connectedProfileEmptyState) return;
        connectedProfileEmptyState.innerHTML = `
            <div class="mb-2"><i class="bi bi-person-bounding-box fs-2"></i></div>
            <strong>${message}</strong>
            <div class="small mt-2">连接账号后，这里会展示区域、代理与租户创建时间等详情。</div>
        `;
        connectedProfileEmptyState.classList.remove('d-none');
        connectedProfileDetails.classList.add('d-none');
        if (connectedProfileStatusBadge) {
            connectedProfileStatusBadge.innerHTML = '<span class="badge bg-secondary">未连接</span>';
        }
        if (profilesModalCurrentStatus) profilesModalCurrentStatus.classList.add('d-none');
    }

    async function checkSession(shouldRefreshInstances = true) {
        try {
            const data = await apiRequest('/oci/api/session');

            document.querySelectorAll('#profileList tr').forEach(r => {
                r.classList.remove('table-active', 'profile-disabled');
            });

            if (data.logged_in && data.alias) {
                // ✨ 加上检查：只有当标签存在时才更新文字
                if (currentProfileStatus) {
                    currentProfileStatus.textContent = `已连接: ${data.alias}`;
                }
                
                if (actionAreaProfile) {
                    actionAreaProfile.textContent = `当前账号: ${data.alias}`;
                    actionAreaProfile.classList.remove('d-none');
                }

                if (profilesModalCurrentStatus) {
                    profilesModalCurrentStatus.textContent = `当前账号: ${data.alias}`;
                    profilesModalCurrentStatus.classList.remove('d-none');
                    profilesModalCurrentStatus.className = 'badge bg-success-subtle text-success border border-success-subtle';
                }
                
                enableMainControls(true, data.can_create);
                await renderConnectedProfileDetails(data.alias);
                await refreshDashboardSummaries(data.alias);

                if (shouldRefreshInstances) {
                    await refreshInstances(true);
                }

                const activeRow = document.querySelector(`#profileList tr[data-alias="${data.alias}"]`);
                if (activeRow) {
                    activeRow.classList.add('table-active', 'profile-disabled');
                }
            } else {
                // ✨ 同样加上检查
                if (currentProfileStatus) {
                    currentProfileStatus.textContent = '未连接';
                }
                
                if (actionAreaProfile) {
                    actionAreaProfile.classList.add('d-none');
                }

                if (profilesModalCurrentStatus) {
                    profilesModalCurrentStatus.className = 'badge bg-secondary-subtle text-secondary border border-secondary-subtle';
                    profilesModalCurrentStatus.classList.add('d-none');
                }
                enableMainControls(false, false);
                resetConnectedProfileDetails();
                await refreshDashboardSummaries();
            }
        } catch (error) {
            // ✨ 错误处理也加上检查
            if (currentProfileStatus) {
                currentProfileStatus.textContent = '未连接 (会话检查失败)';
            }
            
            if (actionAreaProfile) {
                actionAreaProfile.classList.add('d-none');
            }
            
            if (profilesModalCurrentStatus) {
                profilesModalCurrentStatus.className = 'badge bg-danger-subtle text-danger border border-danger-subtle';
                profilesModalCurrentStatus.classList.add('d-none');
            }
            enableMainControls(false, false);
            resetConnectedProfileDetails('当前账户状态检查失败');
            await refreshDashboardSummaries();
        }
    }
    
    function enableMainControls(enabled, canCreate) {
        refreshInstancesBtn.disabled = !enabled;
        createInstanceBtn.disabled = !canCreate;
        networkSettingsBtn.disabled = !enabled;
        const networkSettingsHubBtn = document.getElementById('networkSettingsHubBtn');
        if (networkSettingsHubBtn) networkSettingsHubBtn.disabled = !enabled;

        if (disconnectAccountBtn) {
            disconnectAccountBtn.disabled = !enabled;
        }

        if (!enabled) {
            instanceList.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-5">请先连接一个账号并刷新列表</td></tr>`;
            Object.values(instanceActionButtons).forEach(btn => btn.disabled = true);
        }
    }

    function pollTaskStatus(taskId, isRepoll = false) {
        if (!window.taskPollers) window.taskPollers = {};

        const poller = async () => {
            try {
                const apiResponse = await apiRequest(`/oci/api/task_status/${taskId}`);
                if (!apiResponse || apiResponse.status === 'not_found') {
                    console.warn(`Task ${taskId} not found or invalid response. Stopping poller.`);
                    delete window.taskPollers[taskId];
                    return;
                }
                const isFinalState = ['success', 'failure'].includes(apiResponse.status);

                if (apiResponse.type === 'snatch') {
                    handleSnatchTaskPolling(taskId, apiResponse, isFinalState, isRepoll);
                } else {
                    const lastLogKey = `lastLog_main_${taskId}`;
                    if (window[lastLogKey] !== apiResponse.result) {
                        const logType = apiResponse.status === 'success' ? 'success' : (apiResponse.status === 'failure' ? 'error' : 'info');
                        addLog(`任务[${taskId.substring(0,8)}] ${apiResponse.result}`, logType);
                        window[lastLogKey] = apiResponse.result;
                    }
                }

                if (!isFinalState) {
                    if (apiResponse.status === 'paused') {
                        delete window.taskPollers[taskId];
                        return;
                    }
                    window.taskPollers[taskId] = setTimeout(poller, 5000);
                } else {
                    delete window.taskPollers[taskId];
                    const lastLogKey = `lastLog_main_${taskId}`;
                    const lastSnatchLogKey = `lastSnatchLog_${taskId}`;
                    delete window[lastLogKey];
                    delete window[lastSnatchLogKey];

                    if (apiResponse.status === 'success') {
                        // 静默无感刷新表格
                        setTimeout(() => refreshInstances(true), 2000);
                    }
                }

            } catch (error) {
                addLog(`监控任务 ${taskId} 时发生网络错误，将在10秒后重试...`, 'warning');
                window.taskPollers[taskId] = setTimeout(poller, 10000);
            }
        };

        poller();
    }

    function handleSnatchTaskPolling(taskId, apiResponse, isFinalState, isRepoll) {
        const lastLogKey = `lastSnatchLog_${taskId}`;
        let parsedResult = null;
        let currentMessage = apiResponse.result;

        try {
            parsedResult = JSON.parse(apiResponse.result);
            if (parsedResult && parsedResult.details) {
                const taskName = parsedResult.details.display_name_prefix || parsedResult.details.name;
                if (parsedResult.attempt_count > 0) {
                    currentMessage = `任务 ${taskName}: 第 ${parsedResult.attempt_count} 次尝试，${parsedResult.last_message}`;
                } else {
                    currentMessage = `任务 ${taskName}: ${parsedResult.last_message}`;
                }
            }
        } catch (e) { /* Not JSON, keep original message */ }

        const taskListItem = document.querySelector(`li[data-task-id="${taskId}"]`);
        if (taskListItem) {
            const statusTextEl = taskListItem.querySelector('.text-info-emphasis');
            if (statusTextEl) {
                const msgToDisplay = parsedResult ? parsedResult.last_message : apiResponse.result;
                statusTextEl.innerHTML = `<strong>最新状态:</strong> ${msgToDisplay}`;
            }

            const badgeEl = taskListItem.querySelector('.badge.bg-warning');
            if (badgeEl && parsedResult && parsedResult.attempt_count > 0) {
                badgeEl.textContent = `第 ${parsedResult.attempt_count} 次尝试`;
            }

            if (isFinalState) {
                const progressBar = taskListItem.querySelector('.progress-bar');
                if (progressBar) {
                    progressBar.classList.remove('progress-bar-animated', 'progress-bar-striped');
                    progressBar.classList.add(apiResponse.status === 'success' ? 'bg-success' : 'bg-danger');
                }
                if (badgeEl) {
                    badgeEl.className = `badge ${apiResponse.status === 'success' ? 'bg-success' : 'bg-danger'} text-white`;
                    badgeEl.textContent = apiResponse.status === 'success' ? '成功' : '失败';
                }
            }
        }

        if(window[lastLogKey] === currentMessage) return;
        window[lastLogKey] = currentMessage;

        const accountAlias = parsedResult?.details?.account_alias;
        const taskNameForLog = parsedResult?.details?.display_name_prefix || parsedResult?.details?.name || taskId.substring(0,8);

        if (apiResponse.status === 'running' || apiResponse.status === 'paused') {
            if (apiResponse.status === 'running' && !isRepoll && !snatchTaskAnnounced[taskId]) {
                addLog(`任务 [${taskNameForLog}] 正在准备...`);
                addLog(`抢占任务已成功启动，具体详情请点击【查看抢占任务】`, 'success');
                snatchTaskAnnounced[taskId] = true;
            }
            addSnatchLog(currentMessage, accountAlias);
        } else if (isFinalState) {
            const logType = apiResponse.status === 'success' ? 'success' : 'error';
            addLog(`抢占任务 [${taskNameForLog}] 已完成: ${apiResponse.result}`, logType);
            addSnatchLog(`<strong>任务完成:</strong> ${apiResponse.result}`, accountAlias);
            delete snatchTaskAnnounced[taskId];

            setTimeout(() => {
                // ⭐ 修复点：无论任务窗口是否打开，都强制静默刷新后台数据以更新主面板的数字 ⭐
                loadSnatchTasks();
            }, 3000);
        } else {
            addLog(`任务 [${taskNameForLog}] 状态: ${apiResponse.status} - ${apiResponse.result}`);
        }
    }

    async function loadProfiles() {
        // ⭐ 移除这里的“正在加载”以实现切换页面时的静默无感更新
        try {
            const profiles = await apiRequest(`/oci/api/profiles`);

            if (profiles.length === 0) {
                profileList.innerHTML = `<tr><td colspan="6" class="text-center text-muted py-5"><div class="mb-2"><i class="bi bi-person-x fs-3"></i></div><div>未找到账号，请点击右上角添加</div></td></tr>`;
                updateStatCards({ profileCount: 0 });
                return;
            }

            const savedOrderStr = localStorage.getItem('oci_profiles_order');
            let savedOrder = [];
            if (savedOrderStr) {
                try { savedOrder = JSON.parse(savedOrderStr); } catch(e) {}
            }

            if (savedOrder.length > 0) {
                profiles.sort((a, b) => {
                    const idxA = savedOrder.indexOf(a.alias);
                    const idxB = savedOrder.indexOf(b.alias);
                    if (idxA === -1 && idxB === -1) return 0;
                    if (idxA === -1) return 1;
                    if (idxB === -1) return -1;
                    return idxA - idxB;
                });
            }

            profileList.innerHTML = '';
            profiles.forEach(p => {
                const tr = document.createElement('tr');
                tr.dataset.alias = p.alias;
                tr.dataset.regDate = p.registration_date || '';

                let dateDisplay = '';
                if (p.registration_date && p.days_elapsed !== undefined) {
                    dateDisplay = `<span class="text-success" style="font-weight:500;">${p.registration_date} (${p.days_elapsed}天)</span>`;
                } else {
                    dateDisplay = `<span class="text-muted small">待同步 (连接后自动获取)</span>`;
                }

                let cachedTenancy = localStorage.getItem('oci_tenancy_' + p.alias);
                if (!cachedTenancy || cachedTenancy.startsWith('ocid1.')) {
                    cachedTenancy = '-';
                }

                let cachedUser = localStorage.getItem('oci_user_' + p.alias);
                if (!cachedUser || cachedUser.startsWith('ocid1.')) {
                    cachedUser = '-';
                }

                tr.innerHTML = `
                    <td class="text-center align-middle">
                        <input class="form-check-input profile-checkbox" type="checkbox" value="${p.alias}">
                    </td>
                    <td class="drag-handle text-center align-middle"><i class="bi bi-grip-vertical"></i></td>
                    <td class="align-middle">
                        <a href="#" class="btn btn-outline-info btn-sm manage-profile-btn" data-alias="${p.alias}" style="width: 100%; text-align: left; font-weight: bold; background: rgba(14, 165, 233, 0.1); border-color: rgba(14, 165, 233, 0.3); color: #bae6fd;">
                            <i class="bi bi-gear-fill me-2 text-info"></i> ${p.alias}
                        </a>
                    </td>
                    <td class="text-center align-middle"><div class="text-truncate mx-auto text-center" style="max-width: 120px; font-size: 0.85rem;" title="${cachedTenancy}" id="row-tenancy-${p.alias}">${cachedTenancy}</div></td>
                    <td class="text-center align-middle"><div class="text-truncate mx-auto text-center" style="max-width: 280px; font-size: 0.85rem;" title="${cachedUser}" id="row-user-${p.alias}">${cachedUser}</div></td>
                    <td class="text-center align-middle" style="white-space: nowrap;">${dateDisplay}</td>
                `;

                profileList.appendChild(tr);
            });

            updateStatCards({ profileCount: profiles.length });

            if (document.getElementById('selectAllProfiles')) {
                document.getElementById('selectAllProfiles').checked = false;
            }
            updateBatchDeleteBtnVisibility();

            if (typeof Sortable !== 'undefined' && !profileList.dataset.sortableInitialized) {
                Sortable.create(profileList, {
                    handle: '.drag-handle',
                    animation: 150,
                    onEnd: function() {
                        const order = Array.from(profileList.children).map(tr => tr.dataset.alias);
                        localStorage.setItem('oci_profiles_order', JSON.stringify(order));
                    }
                });
                profileList.dataset.sortableInitialized = 'true';
            }

        } catch (error) {
            console.error(error);
            profileList.innerHTML = `<tr><td colspan="6" class="text-center text-danger py-5"><div class="mb-2"><i class="bi bi-exclamation-triangle fs-3"></i></div><div>加载账号列表失败</div></td></tr>`;
        }
    }

    function formatElapsedTime(startTimeString) {
        const startTime = new Date(startTimeString);
        const now = new Date();
        let seconds = Math.floor((now - startTime) / 1000);
        if (seconds < 60) return `不到1分钟`;
        const days = Math.floor(seconds / (3600 * 24));
        seconds -= days * 3600 * 24;
        const hours = Math.floor(seconds / 3600);
        seconds -= hours * 3600;
        const minutes = Math.floor(seconds / 60);
        let parts = [];
        if (days > 0) parts.push(`${days}天`);
        if (hours > 0) parts.push(`${hours}小时`);
        if (minutes > 0) parts.push(`${minutes}分钟`);
        return parts.join('') || '不到1分钟';
    }

    function formatDuration(startTimeString, endTimeString) {
        if (!startTimeString || !endTimeString) {
            return '未知';
        }
        const startTime = new Date(startTimeString);
        const endTime = new Date(endTimeString);
        let seconds = Math.floor((endTime - startTime) / 1000);

        if (isNaN(seconds) || seconds < 0) return '未知';
        if (seconds < 60) return `${seconds}秒`;

        const days = Math.floor(seconds / (3600 * 24));
        seconds -= days * 3600 * 24;
        const hours = Math.floor(seconds / 3600);
        seconds -= hours * 3600;
        const minutes = Math.floor(seconds / 60);

        let parts = [];
        if (days > 0) parts.push(`${days}天`);
        if (hours > 0) parts.push(`${hours}小时`);
        if (minutes > 0) parts.push(`${minutes}分钟`);

        return parts.join('') || '不到1分钟';
    }

    async function loadTgConfig() {
        try {
            const config = await apiRequest('/oci/api/tg-config');
            tgBotTokenInput.value = config.bot_token || '';
            tgChatIdInput.value = config.chat_id || '';
            updateStatCards({ tgConfigured: !!(config.bot_token || config.chat_id) });
        } catch (error) {
            addLog('加载 Telegram 配置失败。', 'warning');
        }
    }

    async function loadCloudflareConfig() {
        try {
            const config = await apiRequest('/oci/api/cloudflare-config');
            cloudflareApiTokenInput.value = config.api_token || '';
            cloudflareZoneIdInput.value = config.zone_id || '';
            cloudflareDomainInput.value = config.domain || '';
            updateStatCards({ cloudflareConfigured: !!(config.api_token || config.zone_id || config.domain) });
        } catch (error) {
            addLog('加载 Cloudflare 配置失败。', 'warning');
        }
    }

    saveTgConfigBtn.addEventListener('click', async () => {
        const token = tgBotTokenInput.value.trim();
        const chatId = tgChatIdInput.value.trim();
        if (!token || !chatId) return addLog('Bot Token 和 Chat ID 均不能为空。', 'error');

        const spinner = saveTgConfigBtn.querySelector('.spinner-border');
        saveTgConfigBtn.disabled = true;
        spinner.classList.remove('d-none');
        try {
            const response = await apiRequest('/oci/api/tg-config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ bot_token: token, chat_id: chatId })
            });
            addLog(response.message, 'success');
            updateStatCards({ tgConfigured: true });
        } finally {
            saveTgConfigBtn.disabled = false;
            spinner.classList.add('d-none');
        }
    });

    saveCloudflareConfigBtn.addEventListener('click', async () => {
        const apiToken = cloudflareApiTokenInput.value.trim();
        const zoneId = cloudflareZoneIdInput.value.trim();
        const domain = cloudflareDomainInput.value.trim();
        if (!apiToken || !zoneId || !domain) {
            return addLog('Cloudflare API 令牌、Zone ID 和主域名均不能为空。', 'error');
        }

        const spinner = saveCloudflareConfigBtn.querySelector('.spinner-border');
        saveCloudflareConfigBtn.disabled = true;
        spinner.classList.remove('d-none');
        try {
            const response = await apiRequest('/oci/api/cloudflare-config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ api_token: apiToken, zone_id: zoneId, domain: domain })
            });
            addLog(response.message, 'success');
            updateStatCards({ cloudflareConfigured: true });
            cloudflareSettingsModal.hide();
        } finally {
            saveCloudflareConfigBtn.disabled = false;
            spinner.classList.add('d-none');
        }
    });

    async function loadXuiConfig() {
        try {
            const config = await apiRequest('/oci/api/xui-config');
            xuiManagerUrlInput.value = config.manager_url || '';
            xuiManagerSecretInput.value = config.manager_secret || '';
        } catch (error) {
            addLog('加载 X-UI 配置失败，请检查后端。', 'warning');
        }
    }

    saveXuiConfigBtn.addEventListener('click', async () => {
        const url = xuiManagerUrlInput.value.trim();
        const secret = xuiManagerSecretInput.value.trim();

        const spinner = saveXuiConfigBtn.querySelector('.spinner-border');
        saveXuiConfigBtn.disabled = true;
        spinner.classList.remove('d-none');

        try {
            const response = await apiRequest('/oci/api/xui-config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ manager_url: url, manager_secret: secret })
            });
            addLog(response.message, 'success');
        } catch (e) {
            alert(e.message);
        } finally {
            saveXuiConfigBtn.disabled = false;
            spinner.classList.add('d-none');
        }
    });

    getApiKeyBtn.addEventListener('click', async () => {
        addLog('正在获取API密钥...');
        try {
            const data = await apiRequest('/api/get-app-api-key');
            if (data.api_key) {
                apiKeyInput.value = data.api_key;
                navigator.clipboard.writeText(data.api_key).then(() => {
                    addLog('API密钥已成功复制到剪贴板！', 'success');
                    getApiKeyBtn.textContent = '已复制!';
                    setTimeout(() => { getApiKeyBtn.textContent = '获取/复制密钥'; }, 2000);
                }).catch(() => addLog('自动复制失败，请手动复制。', 'warning'));
            }
        } catch (error) {}
    });

    async function saveProfile(alias, profileData) {
        try {
            await apiRequest('/oci/api/profiles', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ alias, profile_data: profileData })
            });
            addLog(`账号 ${alias} 添加成功!`, 'success');
            [newProfileAlias, newProfileConfigText].forEach(el => el.value = '');
            newProfileKeyFile.value = '';
            document.getElementById('accountSshKeyFile').value = '';
            addAccountModal.hide();
            loadProfiles();
            checkSession(false);
        } catch (error) {}
    }

    addNewProfileBtnModal.addEventListener('click', () => {
        const alias = newProfileAlias.value.trim();
        const configText = newProfileConfigText.value.trim();
        const sshKeyFile = document.getElementById('accountSshKeyFile').files[0];
        const keyFile = newProfileKeyFile.files[0];

        if (!alias || !configText || !keyFile) {
            addLog('账号名称, 配置信息和私钥文件都不能为空', 'error');
            return;
        }

        addLog(`正在添加账号: ${alias}...`);
        const profileData = {};
        configText.split('\n').forEach(line => {
            const parts = line.split('=').map(p => p.trim());
            if (parts.length === 2) profileData[parts[0]] = parts[1];
        });

        const privateKeyReader = new FileReader();
        privateKeyReader.onload = (event) => {
            profileData['key_content'] = event.target.result;

            if (sshKeyFile) {
                addLog('正在读取上传的 SSH 公钥...', 'info');
                const publicKeyReader = new FileReader();
                publicKeyReader.onload = (e) => {
                    profileData['default_ssh_public_key'] = e.target.result;
                    saveProfile(alias, profileData);
                };
                publicKeyReader.onerror = () => addLog('读取公钥文件失败！', 'error');
                publicKeyReader.readAsText(sshKeyFile);
            } else {
                addLog('未上传SSH公钥，正在尝试使用全局默认公钥...', 'info');
                apiRequest('/oci/api/default-ssh-key').then(response => {
                    if (response.key) {
                        addLog('已应用全局默认公钥。', 'success');
                        profileData['default_ssh_public_key'] = response.key;
                    } else {
                        addLog('未找到全局默认公钥，此账号将不含公钥。', 'warning');
                        profileData['default_ssh_public_key'] = '';
                    }
                    saveProfile(alias, profileData);
                }).catch(error => {
                    addLog('获取全局公钥失败，将保存为空。', 'error');
                    profileData['default_ssh_public_key'] = '';
                    saveProfile(alias, profileData);
                });
            }
        };
        privateKeyReader.onerror = () => addLog('读取私钥文件失败！', 'error');
        privateKeyReader.readAsText(keyFile);
    });

    function pollForRegistrationDate(alias, dateCell) {
        let attempts = 0;
        const maxAttempts = 15;

        const intervalId = setInterval(async () => {
            attempts++;
            try {
                const profileData = await apiRequest(`/oci/api/profiles/${alias}`);

                if (profileData && profileData.registration_date) {
                    clearInterval(intervalId);
                    const regDate = new Date(profileData.registration_date);
                    const now = new Date();
                    const diffTime = Math.abs(now - regDate);
                    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

                    dateCell.innerHTML = `<span class="text-success" style="font-weight:500;">${profileData.registration_date} (${diffDays}天)</span>`;

                    const activeRow = dateCell.closest('tr');
                    if (activeRow) activeRow.dataset.regDate = profileData.registration_date;

                    addLog(`账号 ${alias} 注册时间已自动同步完成！`, 'success');
                }
            } catch (e) {
                console.warn("Polling date failed:", e);
            }

            if (attempts >= maxAttempts) {
                clearInterval(intervalId);
                if (dateCell.innerHTML.includes('spinner')) {
                    dateCell.innerHTML = '<span class="text-muted small">同步超时 (请刷新重试)</span>';
                }
            }
        }, 2000);
    }

    const selectAllProfiles = document.getElementById('selectAllProfiles');
    const batchDeleteProfilesBtn = document.getElementById('batchDeleteProfilesBtn');

    function updateBatchDeleteBtnVisibility() {
        const checked = document.querySelectorAll('.profile-checkbox:checked').length;
        if (batchDeleteProfilesBtn) {
            if (checked > 0) {
                batchDeleteProfilesBtn.disabled = false;
                batchDeleteProfilesBtn.innerHTML = `<i class="bi bi-trash-fill me-1"></i> 删除选中 (${checked})`;
            } else {
                batchDeleteProfilesBtn.disabled = true;
                batchDeleteProfilesBtn.innerHTML = `<i class="bi bi-trash-fill me-1"></i> 删除选中`;
            }
        }
    }

    selectAllProfiles?.addEventListener('change', (e) => {
        document.querySelectorAll('.profile-checkbox').forEach(cb => {
            cb.checked = e.target.checked;
        });
        updateBatchDeleteBtnVisibility();
    });

    profileList.addEventListener('change', (e) => {
        if (e.target.classList.contains('profile-checkbox')) {
            updateBatchDeleteBtnVisibility();
            const allCbs = document.querySelectorAll('.profile-checkbox');
            const checkedCbs = document.querySelectorAll('.profile-checkbox:checked');
            if(selectAllProfiles) {
                selectAllProfiles.checked = (allCbs.length > 0 && allCbs.length === checkedCbs.length);
            }
        }
    });

    batchDeleteProfilesBtn?.addEventListener('click', async () => {
        const checked = Array.from(document.querySelectorAll('.profile-checkbox:checked')).map(cb => cb.value);
        if (checked.length === 0) return;

        if (!confirm(`警告：确定要彻底删除选中的 ${checked.length} 个账号吗？此操作不可恢复！`)) return;

        const originalText = batchDeleteProfilesBtn.innerHTML;
        batchDeleteProfilesBtn.disabled = true;
        batchDeleteProfilesBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 删除中...';

        try {
            addLog(`正在批量删除 ${checked.length} 个账号...`);
            for (const alias of checked) {
                await apiRequest(`/oci/api/profiles/${alias}`, { method: 'DELETE' });
                localStorage.removeItem('oci_tenancy_' + alias);
                localStorage.removeItem('oci_user_' + alias);
            }
            addLog('批量删除成功!', 'success');

            const data = await apiRequest('/oci/api/session').catch(()=>({}));
            if (data && data.logged_in && checked.includes(data.alias)) {
                await apiRequest('/oci/api/session', { method: 'DELETE' }).catch(()=>{});
            }

            if (selectAllProfiles) selectAllProfiles.checked = false;
            loadProfiles();
            checkSession(false);
        } catch (error) {
            addLog('批量删除遇到错误: ' + error.message, 'error');
        } finally {
            batchDeleteProfilesBtn.disabled = false;
            batchDeleteProfilesBtn.innerHTML = originalText;
            updateBatchDeleteBtnVisibility();
        }
    });

    profileList.addEventListener('click', async (e) => {
        const manageBtn = e.target.closest('.manage-profile-btn');
        if (manageBtn) {
            e.preventDefault();
            const alias = manageBtn.dataset.alias;
            addLog(`正在读取账号 [${alias}] 的配置信息...`);

            try {
                const profileData = await apiRequest(`/oci/api/profiles/${alias}`);
                document.getElementById('manageOriginalAlias').value = alias;
                document.getElementById('manageProfileAlias').value = alias;

                const { default_ssh_public_key, key_content, proxy, ...configParts } = profileData;
                document.getElementById('manageProfileConfigText').value = Object.entries(configParts).map(([k, v]) => `${k || ''}=${v || ''}`).join('\n');
                document.getElementById('manageProfileSshKey').value = default_ssh_public_key || '';
                document.getElementById('manageProxyUrl').value = proxy || '';
                document.getElementById('manageProfileKeyFile').value = '';

                document.getElementById('profileManageModalTitle').textContent = `管理账号: ${alias}`;

                const modalEl = document.getElementById('profileManageModal');
                const modalInstance = bootstrap.Modal.getInstance(modalEl) || new bootstrap.Modal(modalEl);
                modalInstance.show();
            } catch (error) {
                addLog('加载账号信息失败: ' + error.message, 'error');
            }
        }
    });

    document.getElementById('modalConnectBtn')?.addEventListener('click', async () => {
        const alias = document.getElementById('manageOriginalAlias').value;
        if (!alias) return;

        addLog(`正在连接到 ${alias}...`);

        const activeRow = document.querySelector(`#profileList tr[data-alias="${alias}"]`);
        const dateCell = activeRow ? activeRow.querySelector('td:nth-child(6)') : null;
        let needsPolling = false;

        if(dateCell) {
            const currentText = dateCell.innerText.trim();
            if(currentText === '' || currentText.includes('待同步')) {
                dateCell.innerHTML = '<div class="spinner-border spinner-border-sm text-secondary"></div> <span class="text-muted small">同步中...</span>';
                needsPolling = true;
            }
        }

        const manageModal = bootstrap.Modal.getInstance(document.getElementById('profileManageModal'));
        if(manageModal) manageModal.hide();
        const hubModal = bootstrap.Modal.getInstance(document.getElementById('profilesHubModal'));
        if(hubModal) hubModal.hide();

        document.querySelectorAll('#profileList tr').forEach(otherRow => {
            otherRow.classList.add('profile-disabled');
        });

        try {
            const response = await apiRequest('/oci/api/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ alias }) });
            addLog(response.message, 'success');

            await checkSession(true);

            if (needsPolling && dateCell) {
                pollForRegistrationDate(alias, dateCell);
            }
        } catch (error) {
            loadProfiles();
        }
    });

    document.getElementById('saveProfileManageBtn')?.addEventListener('click', async () => {
        const originalAlias = document.getElementById('manageOriginalAlias').value;
        const newAlias = document.getElementById('manageProfileAlias').value.trim();
        const configText = document.getElementById('manageProfileConfigText').value.trim();
        const sshKey = document.getElementById('manageProfileSshKey').value.trim();
        const proxyUrl = document.getElementById('manageProxyUrl').value.trim();
        const keyFile = document.getElementById('manageProfileKeyFile').files[0];

        if (!newAlias || !configText) return addLog('账号名称和配置信息不能为空', 'error');

        addLog(`正在保存对账号 ${originalAlias} 的更改...`);
        try {
            const profileData = await apiRequest(`/oci/api/profiles/${originalAlias}`);

            const existingKeys = Object.keys(profileData);
            existingKeys.forEach(k => {
                if (!['default_ssh_public_key', 'key_content', 'proxy', 'registration_date'].includes(k)) {
                    delete profileData[k];
                }
            });

            configText.split('\n').forEach(line => {
                const parts = line.split('=').map(p => p.trim());
                if (parts.length === 2 && parts[0]) profileData[parts[0]] = parts[1];
            });

            profileData['default_ssh_public_key'] = sshKey;
            profileData['proxy'] = proxyUrl;

            const saveChanges = async () => {
                if (originalAlias !== newAlias) {
                    await apiRequest(`/oci/api/profiles/${originalAlias}`, { method: 'DELETE' });
                }
                await apiRequest('/oci/api/profiles', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ alias: newAlias, profile_data: profileData })
                });
                addLog(`账号 ${newAlias} 保存成功!`, 'success');

                const manageModal = bootstrap.Modal.getInstance(document.getElementById('profileManageModal'));
                if(manageModal) manageModal.hide();

                loadProfiles();
                checkSession(false);
            };

            if (keyFile) {
                const reader = new FileReader();
                reader.onload = (event) => { profileData['key_content'] = event.target.result; saveChanges(); };
                reader.readAsText(keyFile);
            } else {
                saveChanges();
            }
        } catch (error) {
            addLog('保存失败: ' + error.message, 'error');
        }
    });

    instanceList.addEventListener('click', (e) => {
        const row = e.target.closest('tr');
        if (!row || !row.dataset.instanceId) return;

        document.querySelectorAll('#instanceList tr.table-active').forEach(r => r.classList.remove('table-active'));
        row.classList.add('table-active');
        selectedInstance = JSON.parse(row.dataset.instanceData);

        // 提取为了独立函数，以支持更新 DOM 后重新计算状态
        updateActionButtonsState();
    });

    async function loadSnatchTasks() {
        stopSnatchTaskBtn.disabled = true;
        resumeSnatchTaskBtn.disabled = true;
        deleteSnatchTaskBtn.disabled = true;
        deleteCompletedBtn.disabled = true;

        try {
            const [running, completed] = await Promise.all([
                apiRequest('/oci/api/tasks/snatching/running'),
                apiRequest('/oci/api/tasks/snatching/completed')
            ]);
            
            if (running && running.length > 0) {
                if (!window.taskPollers) window.taskPollers = {};
                running.forEach(task => {
                    if (task.status === 'running' && !window.taskPollers[task.id]) {
                        pollTaskStatus(task.id, true);
                    }
                });
            }

            // ⭐ 修复点：这里是更新后台主面板 5 Running / 2 Done 卡片的核心代码 ⭐
            updateStatCards({ runningCount: running.length, completedCount: completed.length });

            // 渲染正在运行的任务 (直接重绘 DOM，不再清空出现闪烁)
            runningSnatchTasksList.innerHTML = running.length === 0
                ? '<li class="list-group-item text-muted">没有正在运行或已暂停的任务。</li>'
                : running.map(task => {
                    if (task.result && typeof task.result === 'object' && task.result.details) {
                        const { details, start_time, attempt_count, last_message } = task.result;
                        const taskName = details.display_name_prefix || details.name;
                        const isPaused = task.status === 'paused';
                        const statusBadge = isPaused 
                            ? `<span class="badge bg-secondary">已暂停</span>`
                            : `<span class="badge bg-warning text-dark">第 ${attempt_count} 次尝试</span>`;
                        const progressBar = isPaused
                            ? `<div class="progress" style="height: 5px;"><div class="progress-bar bg-secondary" style="width: 100%"></div></div>`
                            : `<div class="progress" style="height: 5px;"><div class="progress-bar progress-bar-striped progress-bar-animated" style="width: 100%"></div></div>`;
                        
                        const configString = `<strong>配置:</strong> ${details.shape} / ${details.ocpus || 'N/A'} OCPU / ${details.memory_in_gbs || 'N/A'} GB / ${details.boot_volume_size || 'N/A'} GB<br><strong>系统:</strong> ${details.os_name_version}`;

                        return `
                        <li class="list-group-item py-3" style="border-bottom: 1px solid rgba(128, 128, 128, 0.25) !important;" data-task-id="${task.id}" data-task-status="${task.status}">
                            <div class="row align-items-center">
                                <div class="col-auto">
                                    <input class="form-check-input task-checkbox" type="checkbox" data-task-id="${task.id}" style="transform: scale(1.2);">
                                </div>
                                <div class="col-3 col-lg-2 border-end pe-2">
                                    <span class="badge bg-primary text-truncate d-inline-block mb-1" style="max-width: 100%;" title="${task.account_alias}">${task.account_alias}</span>
                                    <div><code style="word-break: break-all;" title="${taskName}">${taskName}</code></div>
                                </div>
                                <div class="col ps-3">
                                    <div class="d-flex justify-content-between align-items-center mb-1">
                                        <div class="small text-muted"><i class="bi bi-clock"></i> 开始于: ${new Date(start_time).toLocaleString()} <span class="mx-2">|</span> 执行时长: ${formatElapsedTime(start_time)}</div>
                                        <div>${statusBadge}</div>
                                    </div>
                                    <div class="oci-task-config p-2 rounded small">${configString}</div>
                                    <div class="mt-2">${progressBar}<p class="mb-0 mt-1 small text-info-emphasis"><strong>最新状态:</strong> ${last_message}</p></div>
                                </div>
                            </div>
                        </li>`;
                    }
                    return `
                    <li class="list-group-item py-3" style="border-bottom: 1px solid rgba(128, 128, 128, 0.25) !important;" data-task-id="${task.id}" data-task-status="${task.status}">
                        <div class="row align-items-center">
                            <div class="col-auto">
                                <input class="form-check-input task-checkbox" type="checkbox" data-task-id="${task.id}" style="transform: scale(1.2);">
                            </div>
                            <div class="col-3 col-lg-2 border-end pe-2">
                                <span class="badge bg-primary text-truncate d-inline-block mb-1" style="max-width: 100%;" title="${task.account_alias}">${task.account_alias}</span>
                                <div><strong class="small" style="word-break: break-all;">${task.name}</strong></div>
                            </div>
                            <div class="col ps-3"><small class="text-muted">${String(task.result)}</small></div>
                        </div>
                    </li>`;
                }).join('');

            // 渲染已完成的任务
            completedSnatchTasksList.innerHTML = completed.length === 0
                ? '<li class="list-group-item text-muted">没有已完成的抢占任务记录。</li>'
                : completed.map(task => {
                    const startTime = task.created_at; 
                    const durationText = formatDuration(startTime, task.completed_at || task.created_at);
                    
                    const timeInfo = `
                        <div class="small text-muted"><i class="bi bi-calendar-check"></i> 完成于: ${new Date(task.completed_at || task.created_at).toLocaleString()} <span class="mx-2">|</span> 总用时: ${durationText}</div>
                    `;

                    return `
                    <li class="list-group-item py-3" style="border-bottom: 1px solid rgba(128, 128, 128, 0.25) !important;" data-task-id="${task.id}">
                        <div class="row align-items-center">
                            <div class="col-auto">
                                <input class="form-check-input task-checkbox" type="checkbox" data-task-id="${task.id}" style="transform: scale(1.2);">
                            </div>
                            <div class="col-3 col-lg-2 border-end pe-2">
                                <span class="badge bg-secondary text-truncate d-inline-block mb-1" style="max-width: 100%;" title="${task.account_alias}">${task.account_alias}</span>
                                <div><strong class="small" style="word-break: break-all;" title="${task.name}">${task.name}</strong></div>
                            </div>
                            <div class="col ps-3 d-flex justify-content-between align-items-center">
                                ${timeInfo}
                                <span class="badge bg-${task.status === 'success' ? 'success' : 'danger'}">${task.status === 'success' ? '成功' : '失败'}</span>
                            </div>
                        </div>
                    </li>`
                }).join('');
                
            updateRunningActionButtons();
            updateCompletedActionButtons();
        } catch (e) {
            runningSnatchTasksList.innerHTML = '<li class="list-group-item list-group-item-danger">加载正在运行任务失败。</li>';
            completedSnatchTasksList.innerHTML = '<li class="list-group-item list-group-item-danger">加载已完成任务失败。</li>';
        }
    }
    
    completedSnatchTasksList.addEventListener('dblclick', async e => {
        const listItem = e.target.closest('li.list-group-item[data-task-id]');
        if (!listItem) return;
        try {
            const data = await apiRequest(`/oci/api/task_status/${listItem.dataset.taskId}`);
            document.getElementById('taskResultModalLabel').textContent = `任务结果: ${listItem.dataset.taskId}`;
            document.getElementById('taskResultModalBody').innerHTML = `<pre>${data.result}</pre>`;
            taskResultModal.show();
        } catch (error) {}
    });

    stopSnatchTaskBtn.addEventListener('click', () => handleTaskAction('stop', '#runningSnatchTasksList'));
    resumeSnatchTaskBtn.addEventListener('click', () => handleTaskAction('resume', '#runningSnatchTasksList'));
    deleteSnatchTaskBtn.addEventListener('click', () => handleTaskAction('delete', '#runningSnatchTasksList'));
    deleteCompletedBtn.addEventListener('click', () => handleTaskAction('delete', '#completedSnatchTasksList'));

    document.getElementById('selectAllRunningTasks').addEventListener('change', (e) => toggleSelectAll(e.target, '#runningSnatchTasksList'));
    document.getElementById('selectAllCompletedTasks').addEventListener('change', (e) => toggleSelectAll(e.target, '#completedSnatchTasksList'));

    runningSnatchTasksList.addEventListener('change', () => updateRunningActionButtons());
    completedSnatchTasksList.addEventListener('change', () => updateCompletedActionButtons());

    function toggleSelectAll(masterCheckbox, listSelector) {
        document.querySelectorAll(`${listSelector} .task-checkbox`).forEach(chk => chk.checked = masterCheckbox.checked);
        if (listSelector === '#runningSnatchTasksList') {
            updateRunningActionButtons();
        } else {
            updateCompletedActionButtons();
        }
    }

    function updateRunningActionButtons() {
        const checked = Array.from(document.querySelectorAll('#runningSnatchTasksList .task-checkbox:checked'));
        if (checked.length === 0) {
            stopSnatchTaskBtn.disabled = true;
            resumeSnatchTaskBtn.disabled = true;
            deleteSnatchTaskBtn.disabled = true;
            return;
        }

        const statuses = checked.map(chk => chk.closest('li').dataset.taskStatus);

        const allPaused = statuses.every(s => s === 'paused');
        const anyRunning = statuses.some(s => s === 'running');
        const anyPaused = statuses.some(s => s === 'paused');

        stopSnatchTaskBtn.disabled = !anyRunning || anyPaused;
        resumeSnatchTaskBtn.disabled = !anyPaused || anyRunning;
        deleteSnatchTaskBtn.disabled = !allPaused;
    }

    function updateCompletedActionButtons() {
        deleteCompletedBtn.disabled = document.querySelectorAll('#completedSnatchTasksList .task-checkbox:checked').length === 0;
    }

    async function handleTaskAction(action, listSelector) {
        const checked = document.querySelectorAll(`${listSelector} .task-checkbox:checked`);
        if (checked.length === 0) return addLog('请先选择任务', 'warning');

        const taskIds = Array.from(checked).map(cb => cb.dataset.taskId);
        const actionTextMap = { 'stop': '暂停', 'delete': '删除', 'resume': '恢复' };
        const actionText = actionTextMap[action];

        confirmActionModalLabel.textContent = `确认${actionText}任务`;
        confirmActionModalBody.textContent = `确定要${actionText}选中的 ${taskIds.length} 个任务吗？`;
        confirmActionModalConfirmBtn.onclick = async () => {
            confirmActionModal.hide();
            addLog(`正在${actionText} ${taskIds.length} 个任务...`);

            try {
                if (action === 'resume') {
                    const response = await apiRequest(`/oci/api/tasks/resume`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ task_ids: taskIds })
                    });
                    addLog(response.message, 'success');
                } else {
                    const endpoint = action === 'stop' ? '/stop' : '';
                    const method = action === 'stop' ? 'POST' : 'DELETE';
                    await Promise.all(taskIds.map(id => apiRequest(`/oci/api/tasks/${id}${endpoint}`, { method })));
                    addLog(`任务${actionText}请求已发送`, 'success');
                }
                loadSnatchTasks();
            } catch (error) {}
        };
        confirmActionModal.show();
    }

    Object.entries(instanceActionButtons).forEach(([key, button]) => {
        if (key !== 'editInstance') button.addEventListener('click', () => performInstanceAction(key.toLowerCase()));
    });

    async function performInstanceAction(action) {
        if (!selectedInstance) return addLog('请先选择一个实例', 'warning');

        let message = `确定要对实例 "${selectedInstance.display_name}" 执行 "${action}" 操作吗?`;
        let title = `请确认: ${action}`;

        if (action === 'addip') {
            title = '确认附加 IP';
            message = `确定要为实例 "${selectedInstance.display_name}" 增加一个公网 IP 吗？\n\n注意：\n1. 这将自动申请一个辅助私有IP和公网IP。\n2. 申请后您需要在 VPS 内部执行一条命令才能生效。`;
        } else if (action === 'terminate') {
            title = `!!! 警告: 终止实例 !!!`;
            message = `此操作无法撤销，确定要终止实例 "${selectedInstance.display_name}" 吗?`;
            confirmActionModalTerminateOptions.classList.remove('d-none');
            confirmDeleteVolumeCheck.checked = false;
        } else {
            confirmActionModalTerminateOptions.classList.add('d-none');
        }

        if (action === 'changeip') message = `确定更换实例 "${selectedInstance.display_name}" 的公网 IP (IPV4) 吗？\n将尝试删除旧临时IP并创建新临时IP。如果已配置Cloudflare，将自动更新DNS解析。`;
        if (action === 'assignipv6') message = `确定要为实例 "${selectedInstance.display_name}" 分配/更换一个 IPV6 地址吗？如果已配置Cloudflare，将自动更新DNS解析。`;

        confirmActionModalLabel.textContent = title;
        confirmActionModalBody.innerHTML = message.replace(/\n/g, '<br>');

        confirmActionModalConfirmBtn.onclick = async () => {
            confirmActionModal.hide();

            if (action === 'addip') {
                addLog(`正在为实例 ${selectedInstance.display_name} 申请附加 IP...`);
                try {
                    const response = await apiRequest('/oci/api/instance/add-secondary-ip', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ instance_id: selectedInstance.id })
                    });
                    addLog(`IP 附加成功! 新公网IP: ${response.public_ip}`, 'success');
                    alert(`✅ IP 附加成功！\n\n公网 IP: ${response.public_ip}\n内网 IP: ${response.private_ip}\n\n⚠️ 请务必登录 VPS 执行以下命令以启用新 IP:\n\n${response.cmd_hint}`);
                    addLog(`📋 请在 VPS 执行: ${response.cmd_hint}`, 'info');
                    
                    // 使用无感静默刷新
                    setTimeout(() => refreshInstances(true), 2000);
                } catch (e) {}
                return;
            }

            const payload = {
                action,
                instance_id: selectedInstance.id,
                instance_name: selectedInstance.display_name,
                vnic_id: selectedInstance.vnic_id,
                subnet_id: selectedInstance.subnet_id,
                preserve_boot_volume: action === 'terminate' ? !confirmDeleteVolumeCheck.checked : undefined
            };
            addLog(`正在为实例 ${selectedInstance.display_name} 提交 ${action} 请求...`);
            try {
                const response = await apiRequest('/oci/api/instance-action', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
                addLog(response.message, 'success');
                if (response.task_id) pollTaskStatus(response.task_id);
            } catch(e) {}
        };
        confirmActionModal.show();
    }

    async function deleteSecondaryIp(ipId, ipAddr) {
        if(!confirm(`确定要删除辅助 IP ${ipAddr} 吗？\n\n1. 此操作将立即从云端移除该私有 IP。\n2. 您可能还需要手动从 VPS 配置文件中删除它，以免网络报错。`)) {
            return;
        }
        addLog(`正在删除辅助 IP ${ipAddr}...`);
        try {
            const response = await apiRequest('/oci/api/instance/delete-secondary-ip', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ private_ip_id: ipId })
            });
            addLog(response.message, 'success');
            editInstanceModal.hide();
            
            // 使用无感静默刷新
            setTimeout(() => refreshInstances(true), 1500);
        } catch (error) { }
    }

    async function deleteIpv6(ipId, ipAddr) {
        if(!confirm(`确定要删除 IPv6 地址 ${ipAddr} 吗？\n\n此操作将立即生效。`)) {
            return;
        }
        addLog(`正在删除 IPv6 ${ipAddr}...`);
        try {
            const response = await apiRequest('/oci/api/instance/delete-ipv6', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ipv6_id: ipId })
            });
            addLog(response.message, 'success');
            editInstanceModal.hide();
            
            // 使用无感静默刷新
            setTimeout(() => refreshInstances(true), 1500);
        } catch (error) { }
    }

    instanceActionButtons.editInstance.addEventListener('click', async () => {
        if (!selectedInstance) return addLog('请先选择一个实例', 'warning');

        editInstanceIpList.innerHTML = '<tr><td colspan="5" class="text-center text-muted small py-2"><div class="spinner-border spinner-border-sm"></div> 正在加载 IPv4...</td></tr>';
        editInstanceIpv6List.innerHTML = '<tr><td colspan="3" class="text-center text-muted small py-2"><div class="spinner-border spinner-border-sm"></div> 正在加载 IPv6...</td></tr>';

        try {
            addLog(`正在获取实例 ${selectedInstance.display_name} 的详细信息...`);
            const details = await apiRequest(`/oci/api/instance-details/${selectedInstance.id}`);

            editDisplayName.value = details.display_name;
            editBootVolumeSize.value = details.boot_volume_size_in_gbs;
            editVpus.value = details.vpus_per_gb;
            editFlexInstanceConfig.classList.toggle('d-none', !details.shape.toLowerCase().includes('flex'));
            if (details.shape.toLowerCase().includes('flex')) {
                editOcpus.value = details.ocpus;
                editMemory.value = details.memory_in_gbs;
            }

            editInstanceIpList.innerHTML = '';
            if (details.ips && details.ips.length > 0) {
                details.ips.forEach(ip => {
                    const isPrimary = ip.is_primary;
                    const deleteBtn = isPrimary ?
                        '<span class="text-muted small" style="cursor: not-allowed;" title="主 IP 不可删除">-</span>' :
                        `<button class="btn btn-sm btn-outline-danger delete-ip-btn" data-ip-id="${ip.id}" data-ip-addr="${ip.private_ip}" title="删除此辅助 IP"><i class="bi bi-trash"></i></button>`;

                    const typeBadge = isPrimary ?
                        '<span class="badge bg-primary">主IP</span>' :
                        '<span class="badge bg-secondary">辅助</span>';

                    const checkboxHtml = isPrimary ?
                        '<input type="checkbox" class="form-check-input" disabled>' :
                        `<input type="checkbox" class="form-check-input ipv4-select" data-id="${ip.id}" data-addr="${ip.private_ip}">`;

                    const row = `
                        <tr>
                            <td>${checkboxHtml}</td>
                            <td>${ip.private_ip}</td>
                            <td>${ip.public_ip || '<span class="text-muted">-</span>'}</td>
                            <td class="text-center">${typeBadge}</td>
                            <td class="text-end">${deleteBtn}</td>
                        </tr>
                    `;
                    editInstanceIpList.insertAdjacentHTML('beforeend', row);
                });

                document.querySelectorAll('.delete-ip-btn').forEach(btn => {
                    btn.addEventListener('click', function() {
                        deleteSecondaryIp(this.dataset.ipId, this.dataset.ipAddr);
                    });
                });
            } else {
                editInstanceIpList.innerHTML = '<tr><td colspan="5" class="text-center text-muted">未找到 IP 信息</td></tr>';
            }

            editInstanceIpv6List.innerHTML = '';
            if (details.ipv6s && details.ipv6s.length > 0) {
                details.ipv6s.forEach(ip => {
                    const checkboxHtml = `<input type="checkbox" class="form-check-input ipv6-select" data-id="${ip.id}" data-addr="${ip.ip_address}">`;

                    const row = `
                        <tr>
                            <td>${checkboxHtml}</td>
                            <td>${ip.ip_address}</td>
                            <td class="text-end">
                                <button class="btn btn-sm btn-outline-danger delete-ipv6-btn" data-ipv6-id="${ip.id}" data-ipv6-addr="${ip.ip_address}" title="删除此 IPv6"><i class="bi bi-trash"></i></button>
                            </td>
                        </tr>
                    `;
                    editInstanceIpv6List.insertAdjacentHTML('beforeend', row);
                });

                document.querySelectorAll('.delete-ipv6-btn').forEach(btn => {
                    btn.addEventListener('click', function() {
                        deleteIpv6(this.dataset.ipv6Id, this.dataset.ipv6Addr);
                    });
                });
            } else {
                editInstanceIpv6List.innerHTML = '<tr><td colspan="3" class="text-center text-muted">未找到 IPv6 信息</td></tr>';
            }

            const selectAllIpv4 = document.getElementById('selectAllIpv4');
            const selectAllIpv6 = document.getElementById('selectAllIpv6');
            if (selectAllIpv4) {
                selectAllIpv4.checked = false;
                selectAllIpv4.onchange = (e) => {
                    document.querySelectorAll('.ipv4-select').forEach(cb => cb.checked = e.target.checked);
                };
            }
            if (selectAllIpv6) {
                selectAllIpv6.checked = false;
                selectAllIpv6.onchange = (e) => {
                    document.querySelectorAll('.ipv6-select').forEach(cb => cb.checked = e.target.checked);
                };
            }

            editInstanceModal.show();
        } catch(error) {
            console.error(error);
            editInstanceIpList.innerHTML = '<tr><td colspan="5" class="text-center text-danger">加载失败</td></tr>';
            editInstanceIpv6List.innerHTML = '<tr><td colspan="3" class="text-center text-danger">加载失败</td></tr>';
        }
    });

    document.getElementById('batchDeleteIpBtn')?.addEventListener('click', async () => {
        const checked = Array.from(document.querySelectorAll('.ipv4-select:checked'));
        if (checked.length === 0) return addLog('请先勾选要删除的辅助 IP', 'warning');
        if (!confirm(`确定要批量删除选中的 ${checked.length} 个辅助 IP 吗？`)) return;
        for (const cb of checked) {
            await deleteSecondaryIp(cb.dataset.id, cb.dataset.addr).catch(() => {});
        }
    });

    document.getElementById('batchDeleteIpv6Btn')?.addEventListener('click', async () => {
        const checked = Array.from(document.querySelectorAll('.ipv6-select:checked'));
        if (checked.length === 0) return addLog('请先勾选要删除的 IPv6 地址', 'warning');
        if (!confirm(`确定要批量删除选中的 ${checked.length} 个 IPv6 地址吗？`)) return;
        for (const cb of checked) {
            await deleteIpv6(cb.dataset.id, cb.dataset.addr).catch(() => {});
        }
    });

    async function handleInstanceUpdateRequest(action, payload) {
        addLog(`正在提交 ${action} 请求...`);
        try {
            const response = await apiRequest('/oci/api/update-instance', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
            addLog(response.message, 'success');
            if (response.task_id) pollTaskStatus(response.task_id);
            editInstanceModal.hide();
            
            // 使用无感静默刷新
            setTimeout(() => refreshInstances(true), 3000);
        } catch(e) {}
    }

    saveDisplayNameBtn.addEventListener('click', () => handleInstanceUpdateRequest('修改名称', { action: 'update_display_name', instance_id: selectedInstance.id, display_name: editDisplayName.value }));
    saveFlexConfigBtn.addEventListener('click', () => handleInstanceUpdateRequest('修改CPU/内存', { action: 'update_shape', instance_id: selectedInstance.id, ocpus: parseInt(editOcpus.value, 10), memory_in_gbs: parseInt(editMemory.value, 10) }));
    saveBootVolumeSizeBtn.addEventListener('click', () => handleInstanceUpdateRequest('修改引导卷大小', { action: 'update_boot_volume', instance_id: selectedInstance.id, size_in_gbs: parseInt(editBootVolumeSize.value, 10) }));
    saveVpusBtn.addEventListener('click', () => handleInstanceUpdateRequest('修改引导卷性能', { action: 'update_boot_volume', instance_id: selectedInstance.id, vpus_per_gb: parseInt(editVpus.value, 10) }));

    let allNetworkResources = [];

    async function loadSecurityListRules(securityListId) {
        if (!securityListId) {
            renderRules('ingress', []);
            renderRules('egress', []);
            return;
        }

        networkRulesSpinner.classList.remove('d-none');
        saveNetworkRulesBtn.disabled = true;
        try {
            const slDetails = await apiRequest(`/oci/api/network/security-list/${securityListId}`);
            currentSecurityList = slDetails;
            renderRules('ingress', slDetails.ingress_security_rules);
            renderRules('egress', slDetails.egress_security_rules);
        } catch (error) {
            addLog(`加载安全列表 ${securityListId} 规则失败`, 'error');
            renderRules('ingress', []);
            renderRules('egress', []);
        } finally {
            networkRulesSpinner.classList.add('d-none');
            saveNetworkRulesBtn.disabled = false;
        }
    }

    vcnSelect.addEventListener('change', () => {
        const selectedVcnId = vcnSelect.value;
        const vcnData = allNetworkResources.find(v => v.vcn_id === selectedVcnId);

        securityListSelect.innerHTML = '';
        if (vcnData && vcnData.security_lists.length > 0) {
            vcnData.security_lists.forEach(sl => {
                const option = new Option(sl.display_name, sl.id);
                securityListSelect.add(option);
            });
            securityListSelect.disabled = false;
            securityListSelect.dispatchEvent(new Event('change'));
        } else {
            securityListSelect.innerHTML = '<option value="">无安全列表</option>';
            securityListSelect.disabled = true;
            loadSecurityListRules(null);
        }
    });

    securityListSelect.addEventListener('change', () => {
        const selectedSlId = securityListSelect.value;
        loadSecurityListRules(selectedSlId);
    });

    document.getElementById('networkSettingsHubBtn')?.addEventListener('click', () => {
        networkConfigHubModal.hide();
        setTimeout(() => networkSettingsModal.show(), 200);
    });

    document.getElementById('cloudflareSettingsBtn')?.addEventListener('click', async () => {
        networkConfigHubModal.hide();
        await loadCloudflareConfig();
        setTimeout(() => cloudflareSettingsModal.show(), 200);
    });

    document.getElementById('tgSettingsBtn')?.addEventListener('click', async () => {
        networkConfigHubModal.hide();
        await loadTgConfig();
        await loadXuiConfig();
        setTimeout(() => tgSettingsModal.show(), 200);
    });

    networkSettingsBtn.addEventListener('click', async () => {
        vcnSelect.innerHTML = '<option value="">正在加载 VCN...</option>';
        securityListSelect.innerHTML = '<option value="">请先选择VCN</option>';
        vcnSelect.disabled = true;
        securityListSelect.disabled = true;
        renderRules('ingress', []);
        renderRules('egress', []);
        networkRulesSpinner.classList.remove('d-none');

        try {
            addLog("正在获取所有网络资源...");
            allNetworkResources = await apiRequest('/oci/api/network/resources');
            networkRulesSpinner.classList.add('d-none');

            if (allNetworkResources.length === 0) {
                vcnSelect.innerHTML = '<option value="">未找到VCN</option>';
                return;
            }

            vcnSelect.innerHTML = '';
            allNetworkResources.forEach(vcn => {
                const option = new Option(vcn.vcn_name, vcn.vcn_id);
                vcnSelect.add(option);
            });
            vcnSelect.disabled = false;

            vcnSelect.dispatchEvent(new Event('change'));

        } catch (error) {
            networkRulesSpinner.classList.add('d-none');
            vcnSelect.innerHTML = '<option value="">加载失败</option>';
            addLog('获取网络资源列表失败。', 'error');
        }
    });

    function renderRules(type, rules) {
        const tableBody = type === 'ingress' ? ingressRulesTable : egressRulesTable;
        tableBody.innerHTML = !rules || rules.length === 0
            ? `<tr><td colspan="5" class="text-center text-muted">没有规则</td></tr>`
            : rules.map(rule => createRuleRow(type, rule).outerHTML).join('');
        tableBody.querySelectorAll('.remove-rule-btn').forEach(btn => btn.onclick = () => btn.closest('tr').remove());
    }

    function createRuleRow(type, rule = {}) {
        const tr = document.createElement('tr');
        tr.className = 'rule-row';
        const sourceOrDest = type === 'ingress' ? (rule.source || '0.0.0.0/0') : (rule.destination || '0.0.0.0/0');
        const protocol = rule.protocol || '6';
        const protocolOptions = {'all': '所有', '1': 'ICMP', '6': 'TCP', '17': 'UDP'};
        const portRange = (options) => ({ min: options?.min || '', max: options?.max || '' });

        const destPorts = portRange(rule.tcp_options ? rule.tcp_options.destination_port_range : (rule.udp_options ? rule.udp_options.destination_port_range : null));

        tr.innerHTML = `
            <td><input class="form-check-input" type="checkbox" data-key="is_stateless" ${rule.is_stateless ? 'checked' : ''}></td>
            <td><input type="text" class="form-control form-control-sm" data-key="${type === 'ingress' ? 'source' : 'destination'}" value="${sourceOrDest}"></td>
            <td><select class="form-select form-select-sm" data-key="protocol">${Object.entries(protocolOptions).map(([k, v]) => `<option value="${k}" ${protocol == k ? 'selected' : ''}>${v}</option>`).join('')}</select></td>
            <td><div class="input-group input-group-sm"><input type="number" class="form-control" placeholder="Min" data-key="dest_port_min" value="${destPorts.min}"><input type="number" class="form-control" placeholder="Max" data-key="dest_port_max" value="${destPorts.max}"></div></td>
            <td><button class="btn btn-sm btn-danger remove-rule-btn"><i class="bi bi-trash"></i></button></td>`;
        return tr;
    }

    addIngressRuleBtn?.addEventListener('click', () => {
        const placeholder = ingressRulesTable.querySelector('td[colspan="5"]');
        if (placeholder) placeholder.parentElement.remove();
        const newRow = createRuleRow('ingress');
        ingressRulesTable.appendChild(newRow);
        newRow.querySelector('.remove-rule-btn').onclick = () => newRow.remove();
    });

    addEgressRuleBtn?.addEventListener('click', () => {
        const placeholder = egressRulesTable.querySelector('td[colspan="5"]');
        if (placeholder) placeholder.parentElement.remove();
        const newRow = createRuleRow('egress');
        egressRulesTable.appendChild(newRow);
        newRow.querySelector('.remove-rule-btn').onclick = () => newRow.remove();
    });

    openFirewallBtn.addEventListener('click', () => {
        let ingressAdded = false;
        let egressAdded = false;

        const currentIngressRules = collectRulesFromTable(ingressRulesTable, 'ingress');
        const ingressExists = currentIngressRules.some(rule => rule.protocol === 'all' && rule.source === '0.0.0.0/0');

        if (!ingressExists) {
            const allowAllIngressRule = { source: '0.0.0.0/0', protocol: 'all', is_stateless: false };
            const ingressPlaceholder = ingressRulesTable.querySelector('td[colspan="5"]');
            if (ingressPlaceholder) ingressPlaceholder.parentElement.remove();
            ingressRulesTable.appendChild(createRuleRow('ingress', allowAllIngressRule));
            ingressAdded = true;
        }

        const currentEgressRules = collectRulesFromTable(egressRulesTable, 'egress');
        const egressExists = currentEgressRules.some(rule => rule.protocol === 'all' && rule.destination === '0.0.0.0/0');

        if (!egressExists) {
            const allowAllEgressRule = { destination: '0.0.0.0/0', protocol: 'all', is_stateless: false };
            const egressPlaceholder = egressRulesTable.querySelector('td[colspan="5"]');
            if (egressPlaceholder) egressPlaceholder.parentElement.remove();
            egressRulesTable.appendChild(createRuleRow('egress', allowAllEgressRule));
            egressAdded = true;
        }

        if (ingressAdded || egressAdded) {
            addLog(`已添加 "允许所有" 的${(ingressAdded && egressAdded) ? '出入站规则' : (ingressAdded ? '入站规则' : '出站规则')}，请点击 "保存更改" 以生效。`, 'warning');
        } else {
            addLog('无需操作，允许所有的出入站规则均已存在。', 'info');
        }
    });

    function collectRulesFromTable(tableBody, type) {
        return Array.from(tableBody.querySelectorAll('.rule-row')).map(tr => {
            const rule = { is_stateless: tr.querySelector('[data-key="is_stateless"]').checked, protocol: tr.querySelector('[data-key="protocol"]').value };
            rule[type === 'ingress' ? 'source' : 'destination'] = tr.querySelector(`[data-key="${type === 'ingress' ? 'source' : 'destination'}"]`).value;
            rule[`${type === 'ingress' ? 'source' : 'destination'}_type`] = 'CIDR_BLOCK';

            if (['6', '17'].includes(rule.protocol)) {
                let dest_min = parseInt(tr.querySelector('[data-key="dest_port_min"]').value, 10);
                let dest_max = parseInt(tr.querySelector('[data-key="dest_port_max"]').value, 10);

                if (!isNaN(dest_min) && isNaN(dest_max)) dest_max = dest_min;
                if (isNaN(dest_min) && !isNaN(dest_max)) dest_min = dest_max;

                const options = {};
                if (!isNaN(dest_min) && !isNaN(dest_max)) {
                    options.destination_port_range = { min: dest_min, max: dest_max };
                }

                if (rule.protocol === '6') rule.tcp_options = options;
                else rule.udp_options = options;
            }
            return rule;
        });
    }

    saveNetworkRulesBtn.addEventListener('click', async () => {
        const slId = securityListSelect.value;
        if (!slId) return addLog('请先选择一个安全列表', 'warning');

        const ingressRules = collectRulesFromTable(ingressRulesTable, 'ingress');
        const egressRules = collectRulesFromTable(egressRulesTable, 'egress');

        saveNetworkRulesBtn.disabled = true;
        const spinner = saveNetworkRulesBtn.querySelector('.spinner-border');
        if (spinner) spinner.classList.remove('d-none');

        try {
            const response = await apiRequest('/oci/api/network/update-security-rules', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    security_list_id: slId,
                    rules: {
                        ingress_security_rules: ingressRules,
                        egress_security_rules: egressRules
                    }
                })
            });
            addLog(response.message || '安全列表更新成功。', 'success');
            await loadSecurityListRules(slId);
        } catch (error) {
            addLog(`更新安全列表失败: ${error.message}`, 'error');
        } finally {
            saveNetworkRulesBtn.disabled = false;
            if (spinner) spinner.classList.add('d-none');
        }
    });

    let aliasSortAsc = true;
    if (sortAccountByAliasHeader) {
        sortAccountByAliasHeader.addEventListener('click', () => {
            const rows = Array.from(profileList.querySelectorAll('tr[data-alias]'));
            rows.sort((a, b) => {
                const aliasA = a.dataset.alias || '';
                const aliasB = b.dataset.alias || '';
                return aliasSortAsc ? aliasA.localeCompare(aliasB, 'zh-CN') : aliasB.localeCompare(aliasA, 'zh-CN');
            });
            rows.forEach(row => profileList.appendChild(row));
            aliasSortAsc = !aliasSortAsc;
            if (sortAliasIcon) sortAliasIcon.className = aliasSortAsc ? 'bi bi-arrow-up text-primary' : 'bi bi-arrow-down text-primary';

            const order = Array.from(profileList.children).map(tr => tr.dataset.alias);
            localStorage.setItem('oci_profiles_order', JSON.stringify(order));
        });
    }

    let dateSortAsc = true;
    if (sortAccountByDateHeader) {
        sortAccountByDateHeader.addEventListener('click', () => {
            const rows = Array.from(profileList.querySelectorAll('tr[data-alias]'));
            rows.sort((a, b) => {
                const dateA = a.dataset.regDate ? new Date(a.dataset.regDate).getTime() : 0;
                const dateB = b.dataset.regDate ? new Date(b.dataset.regDate).getTime() : 0;
                return dateSortAsc ? dateA - dateB : dateB - dateA;
            });
            rows.forEach(row => profileList.appendChild(row));
            dateSortAsc = !dateSortAsc;
            if (sortIcon) sortIcon.className = dateSortAsc ? 'bi bi-arrow-up text-primary' : 'bi bi-arrow-down text-primary';

            const order = Array.from(profileList.children).map(tr => tr.dataset.alias);
            localStorage.setItem('oci_profiles_order', JSON.stringify(order));
        });
    }

    window.addSnatchLog = addSnatchLog;
    window.pollTaskStatus = pollTaskStatus;
    window.loadSnatchTasks = loadSnatchTasks;


    // ==========================================
    // ✨✨✨ 新增：IAM 身份与用户管理逻辑 ✨✨✨
    // ==========================================
    const manageUsersBtn = document.getElementById('manageUsersBtn');
    const userManagementModalEl = document.getElementById('userManagementModal');
    const iamUsersList = document.getElementById('iamUsersList');
    const refreshUsersBtn = document.getElementById('refreshUsersBtn');
    
    // UI 控制
    const showCreateUserBtn = document.getElementById('showCreateUserBtn');
    const createUserFormArea = document.getElementById('createUserFormArea');
    const submitCreateUserBtn = document.getElementById('submitCreateUserBtn');

    // 1. 登录会话联动按钮状态
    // 在原本的 enableMainControls 函数中其实不用改，因为我们用的是 disabled 属性，
    // 我们在这里监听连接成功后手动激活它
    const originalEnableMainControls = enableMainControls;
    enableMainControls = function(enabled, canCreate) {
        originalEnableMainControls(enabled, canCreate);
        if (manageUsersBtn) manageUsersBtn.disabled = !enabled;
    };

    // 2. 加载用户列表
    async function loadIamUsers() {
        if (!iamUsersList) return;
        iamUsersList.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-5"><div class="spinner-border spinner-border-sm"></div> 正在请求甲骨文 API 获取用户列表...</td></tr>';
        
        try {
            const users = await apiRequest('/oci/api/identity/users');
            iamUsersList.innerHTML = '';
            
            if (users.length === 0) {
                iamUsersList.innerHTML = '<tr><td colspan="4" class="text-center text-muted py-4">未找到任何用户</td></tr>';
                return;
            }
            
            users.forEach(user => {
                const tr = document.createElement('tr');
                const statusColor = user.lifecycle_state === 'ACTIVE' ? 'success' : 'secondary';
                
                // 👇 隐藏“无”或者默认的描述，让界面更清爽
                let descHtml = '';
                if (user.description && user.description !== '无' && user.description !== 'Created via Web Panel') {
                    descHtml = `<br><small class="text-muted" style="font-size: 0.75rem;">${user.description}</small>`;
                }
                
                let emailHtml = user.email === '未绑定' 
                    ? `<span class="text-muted small">未绑定</span>` 
                    : `<code class="text-info">${user.email}</code>`;
                
                tr.innerHTML = `
                    <td style="padding-left: 1rem;"><strong class="text-light">${user.name}</strong>${descHtml}</td>
                    <td>${emailHtml}</td>
                    <td class="text-center"><span class="badge bg-${statusColor}">${user.lifecycle_state}</span></td>
                    <td class="text-center">
                        <div class="btn-group btn-group-sm">
                            <button class="btn btn-outline-warning action-reset-pwd" data-id="${user.id}" data-name="${user.name}" title="重置登录密码"><i class="bi bi-key"></i> 重置</button>
                            <button class="btn btn-outline-danger action-clear-2fa" data-id="${user.id}" data-name="${user.name}" title="强制解除所有 2FA 绑定"><i class="bi bi-phone-vibrate"></i> 清 2FA</button>
                            <button class="btn btn-outline-info action-edit-email" data-id="${user.id}" data-name="${user.name}" data-email="${user.email}" title="修改绑定的邮箱"><i class="bi bi-envelope"></i> 邮箱</button>
                        </div>
                    </td>
                `;
                iamUsersList.appendChild(tr);
            });
            
            bindUserActionEvents();
        } catch (error) {
            iamUsersList.innerHTML = `<tr><td colspan="4" class="text-center text-danger py-4">加载失败: ${error.message}</td></tr>`;
        }
    }

    // 3. 绑定操作按钮事件
    function bindUserActionEvents() {
        // 重置密码
        document.querySelectorAll('.action-reset-pwd').forEach(btn => {
            btn.onclick = async () => {
                const name = btn.dataset.name;
                const id = btn.dataset.id;
                if (!confirm(`⚠️ 危险操作！\n\n确定要重置用户 [${name}] 的控制台登录密码吗？\n重置后将生成一个只能使用一次的临时密码，旧密码将立即失效！`)) return;
                
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>...';
                try {
                    const res = await apiRequest(`/oci/api/identity/users/${id}/reset-password`, { method: 'POST' });
                    alert(`✅ 密码重置成功！\n\n用户: ${name}\n一次性临时密码: ${res.new_password}\n\n请立即复制保存此密码，关闭后将无法再次查看！`);
                    addLog(`用户 ${name} 的密码已重置。`, 'success');
                } catch (e) {
                    alert(`❌ 重置失败: ${e.message}`);
                } finally {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="bi bi-key"></i> 重置密码';
                }
            };
        });

        // 清除 2FA
        document.querySelectorAll('.action-clear-2fa').forEach(btn => {
            btn.onclick = async () => {
                const name = btn.dataset.name;
                const id = btn.dataset.id;
                if (!confirm(`🚨 确定要强制清除用户 [${name}] 绑定的所有 2FA (两步验证) 设备吗？\n清除后该用户登录时将不再需要输入验证码！`)) return;
                
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>...';
                try {
                    const res = await apiRequest(`/oci/api/identity/users/${id}/clear-2fa`, { method: 'POST' });
                    alert(`✅ ${res.message}`);
                    addLog(`已清除用户 ${name} 的 2FA 设备。`, 'success');
                } catch (e) {
                    alert(`❌ 清除失败: ${e.message}`);
                } finally {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="bi bi-phone-vibrate"></i> 清除 2FA';
                }
            };
        });

        // 改邮箱
        document.querySelectorAll('.action-edit-email').forEach(btn => {
            btn.onclick = async () => {
                const name = btn.dataset.name;
                const id = btn.dataset.id;
                const oldEmail = btn.dataset.email;
                const newEmail = prompt(`请输入用户 [${name}] 的新绑定邮箱：`, oldEmail !== '未绑定' ? oldEmail : '');
                
                if (newEmail === null || newEmail.trim() === '' || newEmail === oldEmail) return;
                
                btn.disabled = true;
                btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>...';
                try {
                    const res = await apiRequest(`/oci/api/identity/users/${id}/update-email`, { 
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ email: newEmail.trim() })
                    });
                    addLog(`用户 ${name} 的邮箱已更新。`, 'success');
                    loadIamUsers(); // 刷新列表
                } catch (e) {
                    alert(`❌ 更新邮箱失败: ${e.message}`);
                } finally {
                    btn.disabled = false;
                    btn.innerHTML = '<i class="bi bi-envelope"></i> 改邮箱';
                }
            };
        });
    }

    // 4. 监听弹窗与刷新
    if (userManagementModalEl) {
        userManagementModalEl.addEventListener('shown.bs.modal', loadIamUsers);
    }
    if (refreshUsersBtn) {
        refreshUsersBtn.addEventListener('click', loadIamUsers);
    }

    // 5. 创建用户表单交互
    if (showCreateUserBtn) {
        showCreateUserBtn.addEventListener('click', () => {
            createUserFormArea.classList.toggle('d-none');
        });
    }
    
    if (submitCreateUserBtn) {
        submitCreateUserBtn.addEventListener('click', async () => {
            const nameInput = document.getElementById('newUserName');
            const emailInput = document.getElementById('newUserEmail');
            const descInput = document.getElementById('newUserDesc');
            
            if (!nameInput.value.trim()) {
                alert("用户名不能为空！");
                return;
            }
            
            submitCreateUserBtn.disabled = true;
            submitCreateUserBtn.innerHTML = '创建中...';
            
            try {
                const res = await apiRequest('/oci/api/identity/users', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        name: nameInput.value.trim(),
                        email: emailInput.value.trim(),
                        description: descInput.value.trim()
                    })
                });
                alert(`✅ ${res.message}\n\n注意：新用户创建后初始没有密码，请在列表中点击【重置密码】为其生成初始密码！`);
                nameInput.value = '';
                emailInput.value = '';
                createUserFormArea.classList.add('d-none');
                loadIamUsers();
            } catch (e) {
                alert(`❌ 创建失败: ${e.message}`);
            } finally {
                submitCreateUserBtn.disabled = false;
                submitCreateUserBtn.innerHTML = '确认创建';
            }
        });
    }
    // ==========================================

    

    async function initializeOciDashboard() {
        try {
            await loadProfiles();
        } catch (error) {
            console.warn('initializeOciDashboard loadProfiles failed:', error);
        }

        try {
            await loadAndDisplayDefaultKey();
        } catch (error) {
            console.warn('initializeOciDashboard loadAndDisplayDefaultKey failed:', error);
        }

        try {
            await checkSession(true);
        } catch (error) {
            console.warn('initializeOciDashboard checkSession failed:', error);
        }
    }

    initializeOciDashboard();
});
