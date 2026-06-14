/* @ds-bundle: {"format":3,"namespace":"VakedDesignSystem_ca2818","components":[{"name":"Badge","sourcePath":"components/core/Badge.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Card","sourcePath":"components/core/Card.jsx"},{"name":"Input","sourcePath":"components/core/Input.jsx"},{"name":"KindBadge","sourcePath":"components/core/KindBadge.jsx"},{"name":"DiagnosticRow","sourcePath":"components/feedback/DiagnosticRow.jsx"},{"name":"Toast","sourcePath":"components/feedback/Toast.jsx"},{"name":"Tabs","sourcePath":"components/navigation/Tabs.jsx"}],"sourceHashes":{"components/core/Badge.jsx":"6763fa89da91","components/core/Button.jsx":"d2bbc4f97800","components/core/Card.jsx":"74f55d874868","components/core/Input.jsx":"ddb7497ef43c","components/core/KindBadge.jsx":"65077c140d29","components/feedback/DiagnosticRow.jsx":"004d3de0c123","components/feedback/Toast.jsx":"a6bf417df1de","components/navigation/Tabs.jsx":"b5ee116372f9"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.VakedDesignSystem_ca2818 = window.VakedDesignSystem_ca2818 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/core/Badge.jsx
try { (() => {
const VARIANTS = {
  default: {
    background: 'var(--color-bg-raised)',
    borderColor: 'var(--color-border-default)',
    color: 'var(--color-text-secondary)'
  },
  violet: {
    background: 'var(--color-violet-900)',
    borderColor: 'var(--color-violet-700)',
    color: 'var(--color-violet-400)'
  },
  error: {
    background: 'var(--color-red-950)',
    borderColor: 'var(--color-red-600)',
    color: 'var(--color-red-300)'
  },
  warning: {
    background: 'var(--color-orange-900)',
    borderColor: 'var(--color-orange-700)',
    color: 'var(--color-orange-400)'
  },
  success: {
    background: 'var(--color-green-950)',
    borderColor: 'var(--color-green-700)',
    color: 'var(--color-green-400)'
  },
  info: {
    background: 'var(--color-blue-900)',
    borderColor: 'var(--color-blue-800)',
    color: 'var(--color-blue-300)'
  },
  amber: {
    background: 'var(--color-amber-900)',
    borderColor: 'var(--color-amber-700)',
    color: 'var(--color-amber-400)'
  }
};
function Badge({
  variant = 'default',
  children
}) {
  const v = VARIANTS[variant] || VARIANTS.default;
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 'var(--space-3)',
      border: '1px solid',
      borderRadius: 'var(--radius-md)',
      fontFamily: 'var(--font-mono)',
      fontSize: 'var(--text-sm)',
      padding: '1px 7px',
      lineHeight: '1.5',
      whiteSpace: 'nowrap',
      ...v
    }
  }, children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Badge.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
const VARIANTS = {
  ghost: {
    background: 'var(--color-bg-surface)',
    borderColor: 'var(--color-border-default)',
    color: 'var(--color-text-secondary)'
  },
  primary: {
    background: 'var(--color-violet-900)',
    borderColor: 'var(--color-violet-700)',
    color: 'var(--color-violet-300)'
  },
  danger: {
    background: 'var(--color-red-950)',
    borderColor: 'var(--color-red-600)',
    color: 'var(--color-red-300)'
  },
  success: {
    background: 'var(--color-green-950)',
    borderColor: 'var(--color-green-600)',
    color: 'var(--color-green-400)'
  },
  lower: {
    background: 'var(--color-green-950)',
    borderColor: 'var(--color-green-600)',
    color: 'var(--color-green-400)'
  }
};
function Button({
  variant = 'ghost',
  size = 'md',
  disabled = false,
  loading = false,
  onClick,
  children,
  title
}) {
  const variantStyle = VARIANTS[variant] || VARIANTS.ghost;
  const base = {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 'var(--space-4)',
    border: '1px solid',
    borderRadius: 'var(--radius-lg)',
    cursor: disabled || loading ? 'not-allowed' : 'pointer',
    fontFamily: 'var(--font-mono)',
    fontSize: size === 'sm' ? 'var(--text-sm)' : 'var(--text-base)',
    padding: size === 'sm' ? '2px 8px' : '3px 10px',
    lineHeight: '1.6',
    whiteSpace: 'nowrap',
    transition: 'opacity var(--transition-fast), background var(--transition-fast)',
    opacity: disabled || loading ? 0.45 : 1,
    userSelect: 'none',
    ...variantStyle
  };
  return /*#__PURE__*/React.createElement("button", {
    style: base,
    disabled: disabled || loading,
    onClick: onClick,
    title: title,
    onMouseEnter: e => {
      if (!disabled && !loading) e.currentTarget.style.opacity = '0.75';
    },
    onMouseLeave: e => {
      if (!disabled && !loading) e.currentTarget.style.opacity = '1';
    }
  }, loading ? '…' : children);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/Card.jsx
try { (() => {
function Card({
  title,
  children,
  variant = 'default',
  padding = 'md'
}) {
  const backgrounds = {
    default: 'var(--color-bg-surface)',
    raised: 'var(--color-bg-raised)',
    sunken: 'var(--color-bg-sunken)'
  };
  const paddings = {
    none: '0',
    sm: 'var(--space-8) var(--space-10)',
    md: 'var(--space-10) var(--space-12)'
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      background: backgrounds[variant] || backgrounds.default,
      border: '1px solid var(--color-border-hairline)',
      borderRadius: 'var(--radius-xl)',
      overflow: 'hidden'
    }
  }, title && /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'center',
      padding: 'var(--space-6) var(--space-12)',
      background: 'var(--color-bg-overlay)',
      borderBottom: '1px solid var(--color-border-hairline)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: 'var(--font-mono)',
      fontSize: 'var(--text-sm)',
      color: 'var(--color-text-muted)',
      fontWeight: 500
    }
  }, title)), /*#__PURE__*/React.createElement("div", {
    style: {
      padding: paddings[padding] || paddings.md
    }
  }, children));
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Card.jsx", error: String((e && e.message) || e) }); }

// components/core/Input.jsx
try { (() => {
const {
  useState
} = React;
function Input({
  value,
  onChange,
  placeholder,
  disabled = false,
  monospace = true,
  size = 'md',
  type = 'text'
}) {
  const [focused, setFocused] = useState(false);
  const borderColor = focused ? 'var(--color-indigo-500)' : 'var(--color-border-default)';
  return /*#__PURE__*/React.createElement("input", {
    type: type,
    value: value,
    placeholder: placeholder,
    disabled: disabled,
    onChange: e => onChange && onChange(e.target.value),
    onFocus: () => setFocused(true),
    onBlur: () => setFocused(false),
    style: {
      display: 'block',
      width: '100%',
      boxSizing: 'border-box',
      background: 'var(--color-bg-surface)',
      border: `1px solid ${borderColor}`,
      borderRadius: 'var(--radius-xl)',
      color: disabled ? 'var(--color-text-muted)' : 'var(--color-text-primary)',
      fontFamily: monospace ? 'var(--font-mono)' : 'var(--font-body)',
      fontSize: size === 'sm' ? 'var(--text-sm)' : 'var(--text-base)',
      padding: size === 'sm' ? '4px 8px' : '6px 10px',
      outline: 'none',
      transition: 'border-color var(--transition-fast)',
      caretColor: 'var(--cursor-color)',
      opacity: disabled ? 0.5 : 1,
      cursor: disabled ? 'not-allowed' : 'text'
    }
  });
}
Object.assign(__ds_scope, { Input });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Input.jsx", error: String((e && e.message) || e) }); }

// components/core/KindBadge.jsx
try { (() => {
const KIND_CONFIG = {
  runtime: {
    bg: '#7c3aed',
    border: '#6d28d9',
    icon: '⚡',
    label: 'Runtime'
  },
  index: {
    bg: '#0d9488',
    border: '#0f766e',
    icon: '📚',
    label: 'Index'
  },
  catalog: {
    bg: '#0891b2',
    border: '#0e7490',
    icon: '📂',
    label: 'Catalog'
  },
  stream: {
    bg: '#2563eb',
    border: '#1d4ed8',
    icon: '〰',
    label: 'Stream'
  },
  fiber: {
    bg: '#ea580c',
    border: '#c2410c',
    icon: '🔧',
    label: 'Fiber'
  },
  surface: {
    bg: '#16a34a',
    border: '#15803d',
    icon: '🖥',
    label: 'Surface'
  },
  mesh: {
    bg: '#dc2626',
    border: '#b91c1c',
    icon: '🕸',
    label: 'Mesh'
  },
  workflow: {
    bg: '#ca8a04',
    border: '#a16207',
    icon: '🔀',
    label: 'Workflow'
  },
  parallel: {
    bg: '#d97706',
    border: '#b45309',
    icon: '⧖',
    label: 'Parallel'
  },
  schema: {
    bg: '#7c3aed',
    border: '#6d28d9',
    icon: '📋',
    label: 'Schema'
  },
  capability: {
    bg: '#db2777',
    border: '#be185d',
    icon: '🔑',
    label: 'Capability'
  },
  memory: {
    bg: '#4f46e5',
    border: '#4338ca',
    icon: '🧠',
    label: 'Memory'
  },
  device: {
    bg: '#6b7280',
    border: '#4b5563',
    icon: '💾',
    label: 'Device'
  },
  mediaPipeline: {
    bg: '#65a30d',
    border: '#4d7c0f',
    icon: '🎬',
    label: 'MediaPipeline'
  },
  budget: {
    bg: '#0284c7',
    border: '#0369a1',
    icon: '💰',
    label: 'Budget'
  },
  ebpf: {
    bg: '#1e3a5f',
    border: '#142742',
    icon: '🔎',
    label: 'eBPF'
  },
  mcp: {
    bg: '#2e1065',
    border: '#1e0a5c',
    icon: '🔌',
    label: 'MCP'
  },
  service: {
    bg: '#059669',
    border: '#047857',
    icon: '⚙',
    label: 'Service'
  },
  secret: {
    bg: '#9f1239',
    border: '#881337',
    icon: '🔐',
    label: 'Secret'
  },
  ingress: {
    bg: '#1e40af',
    border: '#1e3a8a',
    icon: '🚪',
    label: 'Ingress'
  },
  container: {
    bg: '#075985',
    border: '#0c4a6e',
    icon: '📦',
    label: 'Container'
  },
  engine: {
    bg: '#831843',
    border: '#701a75',
    icon: '🔩',
    label: 'Engine'
  },
  observability: {
    bg: '#052e16',
    border: '#0a3d20',
    icon: '📊',
    label: 'Observability'
  },
  external: {
    bg: '#374151',
    border: '#1f2937',
    icon: '◇',
    label: 'External'
  }
};
const DEFAULT_KIND = {
  bg: '#374151',
  border: '#1f2937',
  icon: '◆',
  label: 'Node'
};
function KindBadge({
  kind,
  label,
  size = 'md'
}) {
  const cfg = KIND_CONFIG[kind] || DEFAULT_KIND;
  const displayLabel = label ?? cfg.label;
  const isSmall = size === 'sm';
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: isSmall ? '3px' : '4px',
      background: cfg.bg,
      border: `1px solid ${cfg.border}`,
      borderRadius: 'var(--radius-md)',
      color: '#ffffff',
      fontFamily: 'var(--font-mono)',
      fontSize: isSmall ? 'var(--text-xs)' : 'var(--text-sm)',
      padding: isSmall ? '1px 5px' : '2px 7px',
      lineHeight: '1.4',
      whiteSpace: 'nowrap',
      fontWeight: 500
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: isSmall ? '9px' : '10px'
    }
  }, cfg.icon), displayLabel);
}
Object.assign(__ds_scope, { KindBadge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/KindBadge.jsx", error: String((e && e.message) || e) }); }

// components/feedback/DiagnosticRow.jsx
try { (() => {
const SEVERITY_CONFIG = {
  error: {
    icon: '✕',
    bg: 'var(--color-red-950)',
    border: 'var(--color-red-900)',
    label: 'var(--color-red-300)',
    code: 'var(--color-red-300)'
  },
  warning: {
    icon: '⚠',
    bg: 'var(--color-orange-900)',
    border: 'var(--color-orange-700)',
    label: 'var(--color-orange-400)',
    code: 'var(--color-orange-400)'
  },
  info: {
    icon: '◈',
    bg: 'var(--color-bg-surface)',
    border: 'var(--color-border-hairline)',
    label: 'var(--color-text-muted)',
    code: 'var(--color-indigo-300)'
  }
};
function DiagnosticRow({
  severity = 'info',
  code,
  message,
  location
}) {
  const cfg = SEVERITY_CONFIG[severity] || SEVERITY_CONFIG.info;
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      alignItems: 'flex-start',
      gap: 'var(--space-8)',
      padding: 'var(--space-6) var(--space-12)',
      background: cfg.bg,
      borderBottom: `1px solid ${cfg.border}`,
      fontFamily: 'var(--font-mono)',
      fontSize: 'var(--text-sm)'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: cfg.label,
      flexShrink: 0,
      lineHeight: 1.6
    }
  }, cfg.icon), /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, code && /*#__PURE__*/React.createElement("span", {
    style: {
      color: cfg.code,
      marginRight: 'var(--space-8)',
      fontWeight: 600
    }
  }, code, ":"), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--color-text-secondary)'
    }
  }, message), location && /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: 'var(--space-8)',
      color: 'var(--color-text-dimmed)',
      fontSize: 'var(--text-xs)'
    }
  }, "[", location, "]")));
}
Object.assign(__ds_scope, { DiagnosticRow });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/DiagnosticRow.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Toast.jsx
try { (() => {
const {
  useState
} = React;
const VARIANTS = {
  success: {
    icon: '✓',
    bg: 'var(--color-green-950)',
    border: 'var(--color-green-700)',
    text: 'var(--color-green-400)'
  },
  error: {
    icon: '✕',
    bg: 'var(--color-red-950)',
    border: 'var(--color-red-600)',
    text: 'var(--color-red-300)'
  },
  warning: {
    icon: '⚠',
    bg: 'var(--color-orange-900)',
    border: 'var(--color-orange-700)',
    text: 'var(--color-orange-400)'
  },
  info: {
    icon: '◈',
    bg: 'var(--color-bg-surface)',
    border: 'var(--color-indigo-500)',
    text: 'var(--color-indigo-300)'
  }
};
function Toast({
  variant = 'info',
  message,
  onDismiss
}) {
  const [visible, setVisible] = useState(true);
  if (!visible) return null;
  const v = VARIANTS[variant] || VARIANTS.info;
  const dismiss = () => {
    setVisible(false);
    onDismiss && onDismiss();
  };
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 'var(--space-8)',
      background: v.bg,
      border: `1px solid ${v.border}`,
      borderRadius: 'var(--radius-xl)',
      padding: 'var(--space-8) var(--space-12)',
      fontFamily: 'var(--font-mono)',
      fontSize: 'var(--text-base)',
      minWidth: '240px',
      maxWidth: '400px',
      boxShadow: 'none'
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      color: v.text,
      flexShrink: 0
    }
  }, v.icon), /*#__PURE__*/React.createElement("span", {
    style: {
      color: 'var(--color-text-secondary)',
      flex: 1,
      lineHeight: 1.4
    }
  }, message), /*#__PURE__*/React.createElement("button", {
    onClick: dismiss,
    style: {
      background: 'transparent',
      border: 'none',
      color: 'var(--color-text-dimmed)',
      cursor: 'pointer',
      fontSize: 'var(--text-base)',
      fontFamily: 'var(--font-mono)',
      padding: '0 var(--space-2)',
      flexShrink: 0,
      lineHeight: 1,
      transition: 'color var(--transition-fast)'
    },
    onMouseEnter: e => {
      e.currentTarget.style.color = 'var(--color-text-primary)';
    },
    onMouseLeave: e => {
      e.currentTarget.style.color = 'var(--color-text-dimmed)';
    }
  }, "\u2715"));
}
Object.assign(__ds_scope, { Toast });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Toast.jsx", error: String((e && e.message) || e) }); }

// components/navigation/Tabs.jsx
try { (() => {
function Tabs({
  tabs,
  activeTab,
  onTabChange
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: 'flex',
      background: 'var(--color-bg-surface)',
      borderBottom: '1px solid var(--color-border-hairline)',
      flexShrink: 0
    }
  }, tabs.map(tab => {
    const isActive = tab.id === activeTab;
    return /*#__PURE__*/React.createElement("button", {
      key: tab.id,
      onClick: () => onTabChange(tab.id),
      title: tab.label,
      style: {
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-4)',
        flex: 1,
        background: 'transparent',
        border: 'none',
        borderBottom: isActive ? '2px solid var(--color-indigo-500)' : '2px solid transparent',
        color: isActive ? 'var(--color-indigo-300)' : 'var(--color-text-dimmed)',
        padding: 'var(--space-8) var(--space-6)',
        cursor: 'pointer',
        fontFamily: 'var(--font-mono)',
        fontSize: 'var(--text-sm)',
        fontWeight: isActive ? 500 : 400,
        transition: 'color var(--transition-fast)',
        whiteSpace: 'nowrap',
        justifyContent: 'center'
      },
      onMouseEnter: e => {
        if (!isActive) e.currentTarget.style.color = 'var(--color-text-secondary)';
      },
      onMouseLeave: e => {
        if (!isActive) e.currentTarget.style.color = 'var(--color-text-dimmed)';
      }
    }, tab.icon && /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: '13px'
      }
    }, tab.icon), tab.label);
  }));
}
Object.assign(__ds_scope, { Tabs });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/Tabs.jsx", error: String((e && e.message) || e) }); }

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.Input = __ds_scope.Input;

__ds_ns.KindBadge = __ds_scope.KindBadge;

__ds_ns.DiagnosticRow = __ds_scope.DiagnosticRow;

__ds_ns.Toast = __ds_scope.Toast;

__ds_ns.Tabs = __ds_scope.Tabs;

})();
