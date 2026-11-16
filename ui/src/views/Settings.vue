<!--
  Copyright (C) 2022 Nethesis S.r.l.
  SPDX-License-Identifier: GPL-3.0-or-later
-->
<template>
  <cv-grid fullWidth>
    <cv-row>
      <cv-column class="page-title">
        <h2>{{ $t("settings.title") }}</h2>
      </cv-column>
    </cv-row>
    <cv-row v-if="error.getConfiguration">
      <cv-column>
        <NsInlineNotification
          kind="error"
          :title="$t('action.get-configuration')"
          :description="error.getConfiguration"
          :showCloseButton="false"
        />
      </cv-column>
    </cv-row>
    <cv-row v-for="warning in warnings" :key="warning">
      <cv-column>
        <NsInlineNotification
          kind="warning"
          :title="$t('settings.warning')"
          :description="$t('settings.warning_' + warning)"
          :showCloseButton="false"
        />
      </cv-column>
    </cv-row>
    <cv-row>
      <cv-column>
        <cv-tile light>
          <cv-form @submit.prevent="configureModule">
            <!-- web interface -->
            <NsTextInput
              :label="$t('settings.postal_fqdn')"
              placeholder="postal.example.org"
              v-model.trim="form.host"
              class="mg-bottom maxwidth"
              :invalid-message="error.host"
              :disabled="busy"
              ref="host"
            />
            <NsToggle
              value="letsEncrypt"
              :label="$t('settings.lets_encrypt')"
              v-model="form.lets_encrypt"
              :disabled="busy"
              class="mg-bottom"
            >
              <template slot="text-left">{{
                $t("settings.disabled")
              }}</template>
              <template slot="text-right">{{
                $t("settings.enabled")
              }}</template>
            </NsToggle>
            <NsToggle
              value="httpToHttps"
              :label="$t('settings.http_to_https')"
              v-model="form.http2https"
              :disabled="busy"
              class="mg-bottom"
            >
              <template #tooltip>{{
                $t("settings.http_to_https_tooltip")
              }}</template>
              <template slot="text-left">{{
                $t("settings.disabled")
              }}</template>
              <template slot="text-right">{{
                $t("settings.enabled")
              }}</template>
            </NsToggle>

            <cv-accordion ref="accordion" class="mg-bottom">
              <!-- SMTP server -->
              <cv-accordion-item>
                <template slot="title">{{
                  $t("settings.smtp_server")
                }}</template>
                <template slot="content">
                  <p class="mg-bottom">
                    {{ $t("settings.smtp_server_description") }}
                  </p>
                  <NsTextInput
                    :label="$t('settings.smtp_hostname')"
                    :placeholder="form.host || 'smtp.example.org'"
                    :helper-text="$t('settings.smtp_hostname_helper')"
                    v-model.trim="form.smtp_hostname"
                    :invalid-message="error.smtp_hostname"
                    :disabled="busy"
                    ref="smtp_hostname"
                    class="mg-bottom maxwidth"
                  />
                  <NsComboBox
                    :title="$t('settings.smtp_port')"
                    :label="$t('settings.smtp_port_placeholder')"
                    :helper-text="$t('settings.smtp_port_helper')"
                    v-model="smtpPort"
                    :options="smtpPortOptions"
                    :auto-filter="false"
                    :auto-highlight="true"
                    :accept-user-input="true"
                    :user-input-label="$t('settings.other_port')"
                    :invalid-message="error.smtp_port"
                    :disabled="busy"
                    ref="smtp_port"
                    class="mg-bottom maxwidth"
                  />
                  <NsInlineNotification
                    v-if="smtpPortUsedBy"
                    kind="warning"
                    :title="$t('settings.smtp_port_conflict_title')"
                    :description="
                      $t('settings.smtp_port_conflict', {
                        port: form.smtp_port,
                        module: smtpPortUsedBy,
                      })
                    "
                    :showCloseButton="false"
                  />
                  <NsInlineNotification
                    v-else-if="Number(form.smtp_port) === 25"
                    kind="info"
                    :title="$t('settings.smtp_port_25_title')"
                    :description="$t('settings.smtp_port_25')"
                    :showCloseButton="false"
                  />
                  <NsToggle
                    value="smtpTls"
                    :label="$t('settings.smtp_tls')"
                    v-model="form.smtp_tls"
                    :disabled="busy"
                    class="mg-bottom"
                  >
                    <template #tooltip>{{
                      $t("settings.smtp_tls_tooltip")
                    }}</template>
                    <template slot="text-left">{{
                      $t("settings.disabled")
                    }}</template>
                    <template slot="text-right">{{
                      $t("settings.enabled")
                    }}</template>
                  </NsToggle>
                  <NsTextInput
                    type="number"
                    :label="$t('settings.max_message_size')"
                    v-model.number="form.max_message_size"
                    :invalid-message="error.max_message_size"
                    :disabled="busy"
                    ref="max_message_size"
                    class="mg-bottom maxwidth"
                  />
                  <h5 class="mg-bottom-sm">{{ $t("settings.dns_records") }}</h5>
                  <p class="mg-bottom-sm">
                    {{ $t("settings.dns_records_description") }}
                  </p>
                  <NsCodeSnippet
                    v-for="record in dnsHints"
                    :key="record"
                    :copyTooltip="$t('settings.copy_to_clipboard')"
                    :copyFeedback="$t('settings.copied')"
                    :moreText="$t('settings.show_more')"
                    :lessText="$t('settings.show_less')"
                    light
                    class="mg-bottom-sm"
                    >{{ record }}</NsCodeSnippet
                  >
                </template>
              </cv-accordion-item>

              <!-- track domains -->
              <cv-accordion-item>
                <template slot="title">{{
                  $t("settings.track_domains")
                }}</template>
                <template slot="content">
                  <p class="mg-bottom">
                    {{
                      $t("settings.track_domains_description", {
                        track: dns.track_domain || "",
                      })
                    }}
                  </p>
                  <p v-if="!trackDomains.length" class="mg-bottom helper">
                    {{ $t("settings.no_track_domains") }}
                  </p>
                  <div
                    v-for="td in trackDomains"
                    :key="td.name"
                    class="track-domain mg-bottom-sm"
                  >
                    <span class="track-name">{{ td.name }}</span>
                    <NsTag
                      :kind="trackStatusKind(td.status)"
                      :label="$t('settings.track_status_' + td.status)"
                      size="sm"
                    />
                  </div>
                </template>
              </cv-accordion-item>

              <!-- delivery -->
              <cv-accordion-item>
                <template slot="title">{{ $t("settings.delivery") }}</template>
                <template slot="content">
                  <NsTextInput
                    v-for="key in deliveryFields"
                    :key="key"
                    type="number"
                    :label="$t('settings.' + key)"
                    :helper-text="$t('settings.' + key + '_helper')"
                    v-model.number="form[key]"
                    :invalid-message="error[key]"
                    :disabled="busy"
                    :ref="key"
                    class="mg-bottom maxwidth"
                  />
                  <NsTextInput
                    :label="$t('settings.helo_hostname')"
                    :helper-text="$t('settings.helo_hostname_helper')"
                    v-model.trim="form.helo_hostname"
                    :invalid-message="error.helo_hostname"
                    :disabled="busy"
                    ref="helo_hostname"
                    class="mg-bottom maxwidth"
                  />
                  <NsToggle
                    value="resentSender"
                    :label="$t('settings.use_resent_sender_header')"
                    v-model="form.use_resent_sender_header"
                    :disabled="busy"
                    class="mg-bottom"
                  >
                    <template slot="text-left">{{
                      $t("settings.disabled")
                    }}</template>
                    <template slot="text-right">{{
                      $t("settings.enabled")
                    }}</template>
                  </NsToggle>
                </template>
              </cv-accordion-item>

              <!-- IP pools -->
              <cv-accordion-item>
                <template slot="title">{{ $t("settings.ip_pools") }}</template>
                <template slot="content">
                  <p class="mg-bottom">
                    {{ $t("settings.ip_pools_description") }}
                  </p>
                  <NsToggle
                    value="ipPools"
                    :label="$t('settings.use_ip_pools')"
                    v-model="form.use_ip_pools"
                    :disabled="busy"
                    class="mg-bottom"
                  >
                    <template slot="text-left">{{
                      $t("settings.disabled")
                    }}</template>
                    <template slot="text-right">{{
                      $t("settings.enabled")
                    }}</template>
                  </NsToggle>
                  <NsInlineNotification
                    v-if="form.use_ip_pools"
                    kind="warning"
                    :title="$t('settings.ip_pools_limits')"
                    :description="$t('settings.ip_pools_limits_description')"
                    :showCloseButton="false"
                  />
                  <h5 class="mg-bottom-sm">
                    {{ $t("settings.node_addresses") }}
                  </h5>
                  <NsInlineNotification
                    v-if="error.listNodeAddresses"
                    kind="error"
                    :title="$t('action.list-node-addresses')"
                    :description="error.listNodeAddresses"
                    :showCloseButton="false"
                  />
                  <cv-skeleton-text
                    v-if="loading.listNodeAddresses"
                    :paragraph="true"
                    :line-count="2"
                  />
                  <template v-else>
                    <p v-if="!nodeAddresses.length" class="mg-bottom">
                      {{ $t("settings.no_node_addresses") }}
                    </p>
                    <NsCodeSnippet
                      v-for="addr in nodeAddresses"
                      :key="addr.address"
                      :copyTooltip="$t('settings.copy_to_clipboard')"
                      :copyFeedback="$t('settings.copied')"
                      :moreText="$t('settings.show_more')"
                      :lessText="$t('settings.show_less')"
                      light
                      class="mg-bottom-sm"
                      >{{ addr.address }} ({{ addr.interface }},
                      {{
                        addr.public
                          ? $t("settings.public")
                          : $t("settings.private")
                      }})</NsCodeSnippet
                    >
                  </template>
                </template>
              </cv-accordion-item>

              <!-- relays -->
              <cv-accordion-item>
                <template slot="title">{{ $t("settings.relays") }}</template>
                <template slot="content">
                  <p class="mg-bottom">
                    {{ $t("settings.relays_description") }}
                  </p>
                  <div
                    v-for="(relay, index) in form.smtp_relays"
                    :key="relay.key"
                    class="row-fields"
                  >
                    <NsTextInput
                      :label="$t('settings.relay_host')"
                      v-model.trim="relay.host"
                      placeholder="relay.example.net"
                      :disabled="busy"
                    />
                    <NsTextInput
                      type="number"
                      :label="$t('settings.relay_port')"
                      v-model.number="relay.port"
                      :disabled="busy"
                      class="port"
                    />
                    <NsComboBox
                      :title="$t('settings.relay_ssl_mode')"
                      :label="$t('settings.relay_ssl_mode')"
                      v-model="relay.ssl_mode"
                      :options="sslModeOptions"
                      :auto-filter="false"
                      :auto-highlight="true"
                      :disabled="busy"
                    />
                    <NsButton
                      kind="ghost"
                      size="small"
                      :icon="TrashCan20"
                      :disabled="busy"
                      @click="form.smtp_relays.splice(index, 1)"
                      >{{ $t("settings.remove") }}</NsButton
                    >
                  </div>
                  <div
                    v-if="error.smtp_relays"
                    class="validation-error mg-bottom"
                  >
                    {{ error.smtp_relays }}
                  </div>
                  <NsButton
                    kind="tertiary"
                    size="small"
                    :icon="Add20"
                    :disabled="busy || form.smtp_relays.length >= 10"
                    @click="addRelay"
                    class="mg-bottom"
                    >{{ $t("settings.add_relay") }}</NsButton
                  >
                  <NsToggle
                    value="relayViaSmarthost"
                    :label="$t('settings.relay_via_cluster_smarthost')"
                    v-model="form.relay_via_cluster_smarthost"
                    :disabled="busy"
                    class="mg-bottom"
                    ref="relay_via_cluster_smarthost"
                  >
                    <template #tooltip>{{
                      $t("settings.relay_via_cluster_smarthost_tooltip")
                    }}</template>
                    <template slot="text-left">{{
                      $t("settings.disabled")
                    }}</template>
                    <template slot="text-right">{{
                      $t("settings.enabled")
                    }}</template>
                  </NsToggle>
                  <NsInlineNotification
                    v-if="error.relay_via_cluster_smarthost"
                    kind="error"
                    :title="$t('settings.relay_via_cluster_smarthost')"
                    :description="error.relay_via_cluster_smarthost"
                    :showCloseButton="false"
                  />
                  <p class="mg-bottom helper">{{ clusterSmarthostText }}</p>
                  <NsToggle
                    value="clusterRelayProvider"
                    :label="$t('settings.cluster_relay_provider')"
                    v-model="form.cluster_relay_provider"
                    :disabled="busy"
                    class="mg-bottom"
                    ref="cluster_relay_provider"
                  >
                    <template #tooltip>{{
                      $t("settings.cluster_relay_provider_tooltip")
                    }}</template>
                    <template slot="text-left">{{
                      $t("settings.disabled")
                    }}</template>
                    <template slot="text-right">{{
                      $t("settings.enabled")
                    }}</template>
                  </NsToggle>
                  <NsInlineNotification
                    v-if="error.cluster_relay_provider"
                    kind="error"
                    :title="$t('settings.cluster_relay_provider')"
                    :description="error.cluster_relay_provider"
                    :showCloseButton="false"
                  />
                  <p
                    v-if="form.cluster_relay_provider"
                    class="mg-bottom helper"
                  >
                    {{
                      $t("settings.cluster_relay_provider_note", {
                        network: clusterNetwork || "-",
                      })
                    }}
                  </p>
                </template>
              </cv-accordion-item>

              <!-- e-mails of Postal itself -->
              <cv-accordion-item>
                <template slot="title">{{ $t("settings.app_smtp") }}</template>
                <template slot="content">
                  <p class="mg-bottom">
                    {{ $t("settings.app_smtp_description") }}
                  </p>
                  <NsComboBox
                    :title="$t('settings.app_smtp_mode')"
                    :label="$t('settings.app_smtp_mode')"
                    v-model="form.app_smtp_mode"
                    :options="appSmtpModeOptions"
                    :auto-filter="false"
                    :auto-highlight="true"
                    :disabled="busy"
                    class="mg-bottom maxwidth"
                  />
                  <template v-if="form.app_smtp_mode === 'custom'">
                    <NsTextInput
                      :label="$t('settings.app_smtp_host')"
                      v-model.trim="form.app_smtp_host"
                      placeholder="smtp.example.net"
                      :invalid-message="error.app_smtp_host"
                      :disabled="busy"
                      ref="app_smtp_host"
                      class="mg-bottom maxwidth"
                    />
                    <NsTextInput
                      type="number"
                      :label="$t('settings.app_smtp_port')"
                      v-model.number="form.app_smtp_port"
                      :invalid-message="error.app_smtp_port"
                      :disabled="busy"
                      ref="app_smtp_port"
                      class="mg-bottom maxwidth"
                    />
                    <NsComboBox
                      :title="$t('settings.app_smtp_tls')"
                      :label="$t('settings.app_smtp_tls')"
                      v-model="form.app_smtp_tls"
                      :options="appSmtpTlsOptions"
                      :auto-filter="false"
                      :auto-highlight="true"
                      :disabled="busy"
                      class="mg-bottom maxwidth"
                    />
                    <NsToggle
                      value="appSmtpTlsVerify"
                      :label="$t('settings.app_smtp_tls_verify')"
                      v-model="form.app_smtp_tls_verify"
                      :disabled="busy"
                      class="mg-bottom"
                    >
                      <template slot="text-left">{{
                        $t("settings.disabled")
                      }}</template>
                      <template slot="text-right">{{
                        $t("settings.enabled")
                      }}</template>
                    </NsToggle>
                    <NsTextInput
                      :label="$t('settings.username')"
                      v-model.trim="form.app_smtp_username"
                      :disabled="busy"
                      ref="app_smtp_username"
                      class="mg-bottom maxwidth"
                    />
                    <NsTextInput
                      v-if="form.app_smtp_username"
                      type="password"
                      autocomplete="new-password"
                      :label="$t('settings.password')"
                      v-model="secrets.app_smtp_password"
                      :placeholder="
                        secretsSet.app_smtp_password
                          ? $t('settings.unchanged')
                          : ''
                      "
                      :invalid-message="error.app_smtp_password"
                      :disabled="busy"
                      ref="app_smtp_password"
                      class="mg-bottom maxwidth"
                    />
                  </template>
                  <p v-else class="mg-bottom helper">
                    {{ clusterSmarthostText }}
                  </p>
                  <NsTextInput
                    :label="$t('settings.from_name')"
                    placeholder="Postal"
                    v-model="form.from_name"
                    :invalid-message="error.from_name"
                    :disabled="busy"
                    ref="from_name"
                    class="mg-bottom maxwidth"
                  />
                  <NsTextInput
                    :label="$t('settings.from_address')"
                    :placeholder="'postal@' + (form.host || 'example.org')"
                    v-model.trim="form.from_address"
                    :invalid-message="error.from_address"
                    :disabled="busy"
                    ref="from_address"
                    class="mg-bottom maxwidth"
                  />
                </template>
              </cv-accordion-item>

              <!-- OpenID Connect -->
              <cv-accordion-item>
                <template slot="title">{{ $t("settings.oidc") }}</template>
                <template slot="content">
                  <p class="mg-bottom">{{ $t("settings.oidc_description") }}</p>
                  <NsToggle
                    value="oidc"
                    :label="$t('settings.oidc_enabled')"
                    v-model="form.oidc_enabled"
                    :disabled="busy"
                    class="mg-bottom"
                  >
                    <template slot="text-left">{{
                      $t("settings.disabled")
                    }}</template>
                    <template slot="text-right">{{
                      $t("settings.enabled")
                    }}</template>
                  </NsToggle>
                  <template v-if="form.oidc_enabled">
                    <h5 class="mg-bottom-sm">
                      {{ $t("settings.oidc_redirect_uri") }}
                    </h5>
                    <p class="mg-bottom-sm">
                      {{ $t("settings.oidc_redirect_uri_description") }}
                    </p>
                    <NsCodeSnippet
                      :copyTooltip="$t('settings.copy_to_clipboard')"
                      :copyFeedback="$t('settings.copied')"
                      :moreText="$t('settings.show_more')"
                      :lessText="$t('settings.show_less')"
                      light
                      class="mg-bottom"
                      >{{ oidcRedirectUri }}</NsCodeSnippet
                    >
                    <NsComboBox
                      v-if="oidcProviderOptions.length"
                      :title="$t('settings.oidc_preset')"
                      :label="$t('settings.oidc_preset_placeholder')"
                      :helper-text="$t('settings.oidc_preset_helper')"
                      v-model="oidcPreset"
                      :options="oidcProviderOptions"
                      :auto-filter="false"
                      :auto-highlight="true"
                      :disabled="busy"
                      @change="applyOidcPreset"
                      class="mg-bottom maxwidth"
                    />
                    <NsTextInput
                      :label="$t('settings.oidc_name')"
                      v-model.trim="form.oidc_name"
                      :helper-text="$t('settings.oidc_name_helper')"
                      :invalid-message="error.oidc_name"
                      :disabled="busy"
                      ref="oidc_name"
                      class="mg-bottom maxwidth"
                    />
                    <NsTextInput
                      :label="$t('settings.oidc_issuer')"
                      v-model.trim="form.oidc_issuer"
                      placeholder="https://sso.example.org/realms/main"
                      :invalid-message="error.oidc_issuer"
                      :disabled="busy"
                      ref="oidc_issuer"
                      class="mg-bottom maxwidth"
                    />
                    <NsTextInput
                      :label="$t('settings.oidc_identifier')"
                      v-model.trim="form.oidc_identifier"
                      :invalid-message="error.oidc_identifier"
                      :disabled="busy"
                      ref="oidc_identifier"
                      class="mg-bottom maxwidth"
                    />
                    <NsTextInput
                      type="password"
                      autocomplete="new-password"
                      :label="$t('settings.oidc_secret')"
                      v-model="secrets.oidc_secret"
                      :placeholder="
                        secretsSet.oidc_secret ? $t('settings.unchanged') : ''
                      "
                      :invalid-message="error.oidc_secret"
                      :disabled="busy"
                      ref="oidc_secret"
                      class="mg-bottom maxwidth"
                    />
                    <NsTextInput
                      :label="$t('settings.oidc_scopes')"
                      v-model="oidcScopes"
                      :helper-text="$t('settings.oidc_scopes_helper')"
                      :invalid-message="error.oidc_scopes"
                      :disabled="busy"
                      ref="oidc_scopes"
                      class="mg-bottom maxwidth"
                    />
                    <NsTextInput
                      v-for="key in oidcFieldKeys"
                      :key="key"
                      :label="$t('settings.' + key)"
                      v-model.trim="form[key]"
                      :invalid-message="error[key]"
                      :disabled="busy"
                      :ref="key"
                      class="mg-bottom maxwidth"
                    />
                    <NsToggle
                      value="oidcDiscovery"
                      :label="$t('settings.oidc_discovery')"
                      v-model="form.oidc_discovery"
                      :disabled="busy"
                      class="mg-bottom"
                    >
                      <template #tooltip>{{
                        $t("settings.oidc_discovery_tooltip")
                      }}</template>
                      <template slot="text-left">{{
                        $t("settings.disabled")
                      }}</template>
                      <template slot="text-right">{{
                        $t("settings.enabled")
                      }}</template>
                    </NsToggle>
                    <template v-if="!form.oidc_discovery">
                      <NsTextInput
                        v-for="key in oidcEndpointKeys"
                        :key="key"
                        :label="$t('settings.' + key)"
                        v-model.trim="form[key]"
                        placeholder="https://"
                        :invalid-message="error[key]"
                        :disabled="busy"
                        :ref="key"
                        class="mg-bottom maxwidth"
                      />
                    </template>
                  </template>
                  <NsToggle
                    value="localAuth"
                    :label="$t('settings.oidc_local_authentication_enabled')"
                    v-model="form.oidc_local_authentication_enabled"
                    :disabled="busy || !form.oidc_enabled"
                    class="mg-bottom"
                    ref="oidc_local_authentication_enabled"
                  >
                    <template #tooltip>{{
                      $t("settings.oidc_local_authentication_tooltip")
                    }}</template>
                    <template slot="text-left">{{
                      $t("settings.disabled")
                    }}</template>
                    <template slot="text-right">{{
                      $t("settings.enabled")
                    }}</template>
                  </NsToggle>
                  <NsInlineNotification
                    v-if="error.oidc_local_authentication_enabled"
                    kind="error"
                    :title="$t('settings.oidc_local_authentication_enabled')"
                    :description="error.oidc_local_authentication_enabled"
                    :showCloseButton="false"
                  />
                </template>
              </cv-accordion-item>

              <!-- message inspection -->
              <cv-accordion-item>
                <template slot="title">{{
                  $t("settings.inspection")
                }}</template>
                <template slot="content">
                  <p class="mg-bottom">
                    {{ $t("settings.inspection_description") }}
                  </p>
                  <div
                    v-for="svc in inspectionServices"
                    :key="svc"
                    class="mg-bottom"
                  >
                    <NsToggle
                      :value="svc"
                      :label="$t('settings.' + svc + '_enabled')"
                      v-model="form[svc + '_enabled']"
                      :disabled="busy"
                      class="mg-bottom"
                    >
                      <template slot="text-left">{{
                        $t("settings.disabled")
                      }}</template>
                      <template slot="text-right">{{
                        $t("settings.enabled")
                      }}</template>
                    </NsToggle>
                    <template v-if="form[svc + '_enabled']">
                      <div class="row-fields">
                        <NsTextInput
                          :label="$t('settings.service_host')"
                          v-model.trim="form[svc + '_host']"
                          placeholder="10.5.4.1"
                          :invalid-message="error[svc + '_host']"
                          :disabled="busy"
                          :ref="svc + '_host'"
                        />
                        <NsTextInput
                          type="number"
                          :label="$t('settings.service_port')"
                          v-model.number="form[svc + '_port']"
                          :invalid-message="error[svc + '_port']"
                          :disabled="busy"
                          class="port"
                        />
                      </div>
                      <template v-if="svc === 'rspamd'">
                        <NsToggle
                          value="rspamdSsl"
                          :label="$t('settings.rspamd_ssl')"
                          v-model="form.rspamd_ssl"
                          :disabled="busy"
                          class="mg-bottom"
                        >
                          <template slot="text-left">{{
                            $t("settings.disabled")
                          }}</template>
                          <template slot="text-right">{{
                            $t("settings.enabled")
                          }}</template>
                        </NsToggle>
                        <NsTextInput
                          type="password"
                          autocomplete="new-password"
                          :label="$t('settings.rspamd_password')"
                          v-model="secrets.rspamd_password"
                          :placeholder="
                            secretsSet.rspamd_password
                              ? $t('settings.unchanged')
                              : ''
                          "
                          :disabled="busy"
                          class="mg-bottom maxwidth"
                        />
                      </template>
                    </template>
                  </div>
                </template>
              </cv-accordion-item>

              <!-- DNS names -->
              <cv-accordion-item>
                <template slot="title">{{ $t("settings.dns_names") }}</template>
                <template slot="content">
                  <p class="mg-bottom">
                    {{ $t("settings.dns_names_description") }}
                  </p>
                  <NsTextInput
                    :label="$t('settings.dns_mx_records')"
                    v-model="mxRecords"
                    :placeholder="
                      dns.mx_records ? dns.mx_records.join(', ') : ''
                    "
                    :helper-text="$t('settings.comma_separated')"
                    :invalid-message="error.dns_mx_records"
                    :disabled="busy"
                    ref="dns_mx_records"
                    class="mg-bottom maxwidth"
                  />
                  <NsTextInput
                    v-for="key in dnsKeys"
                    :key="key"
                    :label="$t('settings.' + key)"
                    v-model.trim="form[key]"
                    :placeholder="dns[key.replace('dns_', '')] || ''"
                    :invalid-message="error[key]"
                    :disabled="busy"
                    :ref="key"
                    class="mg-bottom maxwidth"
                  />
                </template>
              </cv-accordion-item>

              <!-- processes and logging -->
              <cv-accordion-item>
                <template slot="title">{{
                  $t("settings.performance")
                }}</template>
                <template slot="content">
                  <NsTextInput
                    v-for="key in performanceFields"
                    :key="key"
                    type="number"
                    :label="$t('settings.' + key)"
                    :helper-text="$t('settings.' + key + '_helper')"
                    v-model.number="form[key]"
                    :invalid-message="error[key]"
                    :disabled="busy"
                    :ref="key"
                    class="mg-bottom maxwidth"
                  />
                  <NsToggle
                    v-for="key in loggingToggles"
                    :key="key"
                    :value="key"
                    :label="$t('settings.' + key)"
                    v-model="form[key]"
                    :disabled="busy"
                    class="mg-bottom"
                  >
                    <template slot="text-left">{{
                      $t("settings.disabled")
                    }}</template>
                    <template slot="text-right">{{
                      $t("settings.enabled")
                    }}</template>
                  </NsToggle>
                </template>
              </cv-accordion-item>

              <!-- advanced -->
              <cv-accordion-item>
                <template slot="title">{{ $t("settings.advanced") }}</template>
                <template slot="content">
                  <p class="mg-bottom">
                    {{ $t("settings.initialize_postal_description") }}
                  </p>
                  <NsButton
                    kind="secondary"
                    :icon="Settings20"
                    :loading="loading.initializePostal"
                    :disabled="busy || loading.initializePostal"
                    @click="initializePostal"
                  >
                    {{ $t("settings.initialize_postal") }}
                  </NsButton>
                  <NsInlineNotification
                    v-if="error.initializePostal"
                    kind="error"
                    :title="$t('settings.initialize_postal')"
                    :description="error.initializePostal"
                    :showCloseButton="false"
                  />
                </template>
              </cv-accordion-item>
            </cv-accordion>

            <NsInlineNotification
              v-if="error.configureModule"
              kind="error"
              :title="$t('action.configure-module')"
              :description="error.configureModule"
              :showCloseButton="false"
            />
            <NsButton
              kind="primary"
              :icon="Save20"
              :loading="loading.configureModule"
              :disabled="busy"
              >{{ $t("settings.save") }}</NsButton
            >
          </cv-form>
        </cv-tile>
      </cv-column>
    </cv-row>
  </cv-grid>
</template>

<script>
import to from "await-to-js";
import { mapState } from "vuex";
import {
  QueryParamService,
  UtilService,
  TaskService,
  IconService,
  PageTitleService,
} from "@nethserver/ns8-ui-lib";

const SECRET_FIELDS = ["oidc_secret", "app_smtp_password", "rspamd_password"];

export default {
  name: "Settings",
  mixins: [
    TaskService,
    IconService,
    UtilService,
    QueryParamService,
    PageTitleService,
  ],
  pageTitle() {
    return this.$t("settings.title") + " - " + this.appName;
  },
  data() {
    return {
      q: {
        page: "settings",
      },
      urlCheckInterval: null,
      form: {
        host: "",
        lets_encrypt: false,
        http2https: true,
        smtp_relays: [],
        oidc_scopes: ["openid", "email"],
        dns_mx_records: [],
      },
      secrets: { oidc_secret: "", app_smtp_password: "", rspamd_password: "" },
      secretsSet: {
        oidc_secret: false,
        app_smtp_password: false,
        rspamd_password: false,
      },
      oidcScopes: "openid, email",
      smtpPort: "2525",
      smtpPortChoices: [],
      trackDomains: [],
      mxRecords: "",
      oidcPreset: "",
      oidcProviders: [],
      nodeAddresses: [],
      dns: {},
      clusterSmarthost: {},
      clusterNetwork: "",
      oidcRedirectUri: "",
      warnings: [],
      relayKey: 0,
      deliveryFields: [
        "default_maximum_delivery_attempts",
        "default_maximum_hold_expiry_days",
        "default_suppression_list_automatic_removal_days",
        "default_spam_threshold",
        "default_spam_failure_threshold",
      ],
      performanceFields: [
        "web_server_max_threads",
        "worker_threads",
        "main_db_pool_size",
      ],
      loggingToggles: [
        "logging_enabled",
        "smtp_log_connections",
        "rails_log_enabled",
      ],
      oidcFieldKeys: [
        "oidc_uid_field",
        "oidc_email_address_field",
        "oidc_name_field",
      ],
      oidcEndpointKeys: [
        "oidc_authorization_endpoint",
        "oidc_token_endpoint",
        "oidc_userinfo_endpoint",
        "oidc_jwks_uri",
      ],
      dnsKeys: [
        "dns_spf_include",
        "dns_return_path_domain",
        "dns_route_domain",
        "dns_track_domain",
      ],
      inspectionServices: ["rspamd", "spamd", "clamav"],
      loading: {
        getConfiguration: false,
        configureModule: false,
        initializePostal: false,
        listNodeAddresses: false,
      },
      error: {
        getConfiguration: "",
        configureModule: "",
        initializePostal: "",
        listNodeAddresses: "",
      },
    };
  },
  computed: {
    ...mapState(["instanceName", "core", "appName"]),
    busy() {
      return this.loading.getConfiguration || this.loading.configureModule;
    },
    smtpPortOptions() {
      const choices = this.smtpPortChoices.length
        ? this.smtpPortChoices
        : [{ port: 2525 }, { port: 25 }, { port: 587 }];
      return choices.map((c) => ({
        name: String(c.port),
        value: String(c.port),
        label: c.used_by
          ? this.$t("settings.smtp_port_option_used", {
              port: c.port,
              module: c.used_by,
            })
          : this.$t("settings.smtp_port_option_" + c.port),
      }));
    },
    smtpPortUsedBy() {
      const choice = this.smtpPortChoices.find(
        (c) => c.port === Number(this.form.smtp_port)
      );
      return choice ? choice.used_by : "";
    },
    sslModeOptions() {
      return ["Auto", "STARTTLS", "TLS", "None"].map((v) => ({
        name: v,
        value: v,
        label: this.$t("settings.ssl_mode_" + v.toLowerCase()),
      }));
    },
    appSmtpModeOptions() {
      return ["smarthost", "custom"].map((v) => ({
        name: v,
        value: v,
        label: this.$t("settings.app_smtp_mode_" + v),
      }));
    },
    appSmtpTlsOptions() {
      return ["starttls_auto", "starttls", "none"].map((v) => ({
        name: v,
        value: v,
        label: this.$t("settings.app_smtp_tls_" + v),
      }));
    },
    oidcProviderOptions() {
      return this.oidcProviders.map((p) => ({
        name: p.module_id,
        value: p.module_id,
        label: `${p.name} - ${p.ui_name || p.module_id} (${p.host})`,
      }));
    },
    clusterSmarthostText() {
      const sh = this.clusterSmarthost;
      if (!sh.enabled) {
        return this.$t("settings.cluster_smarthost_disabled");
      }
      return this.$t(
        sh.authenticated
          ? "settings.cluster_smarthost_authenticated"
          : "settings.cluster_smarthost_open",
        { host: sh.host, port: sh.port }
      );
    },
    dnsHints() {
      const host = this.form.host;
      if (!host || !this.dns.mx_records) {
        return [];
      }
      const ip = `<${this.$t("settings.node_public_address")}>`;
      const mx = this.dns.mx_records[0];
      const rp = this.dns.return_path_domain;
      const spf = this.dns.spf_include;
      const records = [`${host} IN A ${ip}`];
      if (mx !== host) {
        records.push(`${mx} IN A ${ip}`);
      }
      records.push(
        `${spf} IN TXT "v=spf1 ip4:${ip} ~all"`,
        `${rp} IN A ${ip}`,
        `${rp} IN MX 10 ${mx}`,
        `${rp} IN TXT "v=spf1 a mx include:${spf} ~all"`,
        `${
          this.form.dns_dkim_identifier || "postal"
        }._domainkey.${rp} IN TXT <${this.$t("settings.dkim_record_command")}>`,
        `${this.dns.route_domain} IN MX 10 ${mx}`,
        `${this.dns.track_domain} IN CNAME ${host}`
      );
      return records;
    },
  },
  watch: {
    smtpPort(value) {
      const port = parseInt(value, 10);
      this.$set(this.form, "smtp_port", isNaN(port) ? value : port);
    },
  },
  created() {
    this.getConfiguration();
    this.listNodeAddresses();
    this.listOidcProviders();
  },
  beforeRouteEnter(to, from, next) {
    next((vm) => {
      vm.watchQueryData(vm);
      vm.urlCheckInterval = vm.initUrlBindingForApp(vm, vm.q.page);
    });
  },
  beforeRouteLeave(to, from, next) {
    clearInterval(this.urlCheckInterval);
    next();
  },
  methods: {
    async runTask(action, data, extra, callbacks) {
      const eventId = this.getUuid();
      for (const [state, cb] of Object.entries(callbacks)) {
        this.core.$root.$once(`${action}-${state}-${eventId}`, cb);
      }
      const res = await to(
        this.createModuleTaskForApp(this.instanceName, {
          action,
          data,
          extra: { ...extra, eventId },
        })
      );
      return res[0];
    },
    async getConfiguration() {
      this.loading.getConfiguration = true;
      this.error.getConfiguration = "";
      const err = await this.runTask(
        "get-configuration",
        undefined,
        {
          title: this.$t("action.get-configuration"),
          isNotificationHidden: true,
        },
        {
          completed: this.getConfigurationCompleted,
          aborted: (taskResult, taskContext) => {
            console.error(`${taskContext.action} aborted`, taskResult);
            this.error.getConfiguration = this.$t("error.generic_error");
            this.loading.getConfiguration = false;
          },
        }
      );
      if (err) {
        this.error.getConfiguration = this.getErrorMessage(err);
        this.loading.getConfiguration = false;
      }
    },
    getConfigurationCompleted(taskContext, taskResult) {
      const config = taskResult.output;
      const form = {};
      for (const [key, value] of Object.entries(config)) {
        if (
          key.endsWith("_set") ||
          [
            "dns",
            "cluster_smarthost",
            "cluster_network",
            "node_address",
            "oidc_redirect_uri",
            "warnings",
            "configured",
            "smtp_hostname_effective",
            "track_domains",
            "smtp_port_choices",
          ].includes(key)
        ) {
          continue;
        }
        form[key] = value;
      }
      form.smtp_relays = (config.smtp_relays || []).map((r) => ({
        ...r,
        key: this.relayKey++,
      }));
      this.form = form;
      this.smtpPort = String(config.smtp_port);
      this.smtpPortChoices = config.smtp_port_choices || [];
      this.trackDomains = config.track_domains || [];
      for (const field of SECRET_FIELDS) {
        this.secretsSet[field] = !!config[field + "_set"];
        this.secrets[field] = "";
      }
      this.oidcScopes = (config.oidc_scopes || []).join(", ");
      this.mxRecords = (config.dns_mx_records || []).join(", ");
      this.dns = config.dns || {};
      this.clusterSmarthost = config.cluster_smarthost || {};
      this.clusterNetwork = config.cluster_network;
      this.oidcRedirectUri = config.oidc_redirect_uri;
      this.warnings = config.warnings || [];
      this.loading.getConfiguration = false;
      this.focusElement("host");
    },
    async listNodeAddresses() {
      this.loading.listNodeAddresses = true;
      this.error.listNodeAddresses = "";
      const err = await this.runTask(
        "list-node-addresses",
        undefined,
        {
          title: this.$t("action.list-node-addresses"),
          isNotificationHidden: true,
        },
        {
          completed: (taskContext, taskResult) => {
            this.nodeAddresses = taskResult.output.addresses || [];
            this.loading.listNodeAddresses = false;
          },
          aborted: () => {
            this.error.listNodeAddresses = this.$t("error.generic_error");
            this.loading.listNodeAddresses = false;
          },
        }
      );
      if (err) {
        this.error.listNodeAddresses = this.getErrorMessage(err);
        this.loading.listNodeAddresses = false;
      }
    },
    async listOidcProviders() {
      await this.runTask(
        "list-oidc-providers",
        undefined,
        {
          title: this.$t("action.list-oidc-providers"),
          isNotificationHidden: true,
        },
        {
          completed: (taskContext, taskResult) => {
            this.oidcProviders = taskResult.output.providers || [];
          },
        }
      );
    },
    applyOidcPreset(moduleId) {
      const provider = this.oidcProviders.find((p) => p.module_id === moduleId);
      if (!provider) {
        return;
      }
      this.form.oidc_name = provider.name;
      this.form.oidc_issuer = provider.issuer;
      this.form.oidc_discovery = true;
      if (!this.form.oidc_identifier) {
        this.form.oidc_identifier = "postal";
      }
      this.focusElement("oidc_issuer");
    },
    trackStatusKind(status) {
      return (
        {
          obtained: "green",
          pending: "high-contrast",
          no_lets_encrypt: "gray",
          used_by_another_route: "red",
        }[status] || "gray"
      );
    },
    addRelay() {
      this.form.smtp_relays.push({
        host: "",
        port: 25,
        ssl_mode: "Auto",
        key: this.relayKey++,
      });
    },
    splitList(value) {
      return (value || "")
        .split(/[\s,]+/)
        .map((x) => x.trim())
        .filter((x) => x);
    },
    validateConfigureModule() {
      this.clearErrors(this);
      if (!this.form.host) {
        this.error.host = this.$t("common.required");
        this.focusElement("host");
        return false;
      }
      if (
        !this.form.oidc_local_authentication_enabled &&
        !this.form.oidc_enabled
      ) {
        this.error.oidc_local_authentication_enabled = this.$t(
          "settings.local_authentication_required"
        );
        return false;
      }
      return true;
    },
    configureModuleValidationFailed(validationErrors) {
      this.loading.configureModule = false;
      let focusAlreadySet = false;
      for (const validationError of validationErrors) {
        const param = validationError.parameter;
        this.$set(
          this.error,
          param,
          this.$t("settings." + validationError.error, {
            value: validationError.value,
          })
        );
        if (!focusAlreadySet) {
          this.focusElement(param);
          focusAlreadySet = true;
        }
      }
    },
    async configureModule() {
      if (!this.validateConfigureModule()) {
        return;
      }
      this.loading.configureModule = true;
      this.error.configureModule = "";
      const data = { ...this.form };
      data.smtp_relays = this.form.smtp_relays
        .filter((r) => r.host)
        .map((r) => ({
          host: r.host,
          port: Number(r.port) || 25,
          ssl_mode: r.ssl_mode || "Auto",
        }));
      data.oidc_scopes = this.splitList(this.oidcScopes);
      data.dns_mx_records = this.splitList(this.mxRecords);
      for (const field of SECRET_FIELDS) {
        if (this.secrets[field]) {
          data[field] = this.secrets[field];
        }
      }
      const err = await this.runTask(
        "configure-module",
        data,
        {
          title: this.$t("settings.instance_configuration", {
            instance: this.instanceName,
          }),
          description: this.$t("settings.configuring"),
        },
        {
          "validation-failed": this.configureModuleValidationFailed,
          completed: () => {
            this.loading.configureModule = false;
            this.getConfiguration();
          },
          aborted: (taskResult, taskContext) => {
            console.error(`${taskContext.action} aborted`, taskResult);
            this.error.configureModule = this.$t("error.generic_error");
            this.loading.configureModule = false;
          },
        }
      );
      if (err) {
        this.error.configureModule = this.getErrorMessage(err);
        this.loading.configureModule = false;
      }
    },
    async initializePostal() {
      this.loading.initializePostal = true;
      this.error.initializePostal = "";
      const err = await this.runTask(
        "initialize-postal",
        {},
        {
          title: this.$t("settings.initialize_postal"),
          description: this.$t("settings.configuring"),
        },
        {
          completed: () => {
            this.loading.initializePostal = false;
          },
          aborted: () => {
            this.error.initializePostal = this.$t("error.generic_error");
            this.loading.initializePostal = false;
          },
        }
      );
      if (err) {
        this.error.initializePostal = this.getErrorMessage(err);
        this.loading.initializePostal = false;
      }
    },
  },
};
</script>

<style scoped lang="scss">
@import "../styles/carbon-utils";
.mg-bottom {
  margin-bottom: $spacing-06;
}

.mg-bottom-sm {
  margin-bottom: $spacing-03;
}

.maxwidth {
  max-width: 38rem;
}

.row-fields {
  display: flex;
  flex-wrap: wrap;
  gap: $spacing-05;
  align-items: flex-end;
  margin-bottom: $spacing-05;
}

.port {
  max-width: 8rem;
}

.helper {
  color: $text-02;
}

.track-domain {
  display: flex;
  align-items: center;
  gap: $spacing-03;
}

.track-name {
  font-family: monospace;
}

.validation-error {
  color: $support-01;
}
</style>
