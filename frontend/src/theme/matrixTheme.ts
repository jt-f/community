import { createTheme, Theme } from '@mui/material/styles';

// Matrix-inspired color palette
const matrixGreen = '#00FF41';
const matrixDarkGreen = '#003B00';
const matrixBlack = '#0D0208';
const matrixCode = '#008F11';
const matrixGlow = '#39FF14';
const matrixBlue = '#00FFFF';
const matrixRed = '#FF073A';
const matrixPurple = '#BC13FE';

// New accent colors
const accentOrange = '#FF8C00';
const accentCobaltBlue = '#0047AB';
const accentOrangeGlow = '#FFA500';
const accentCobaltBlueGlow = '#4169E1';

// Create a futuristic Matrix-inspired theme
export const matrixTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: matrixGreen,
      light: matrixGlow,
      dark: matrixDarkGreen,
      contrastText: matrixBlack,
    },
    secondary: {
      main: matrixBlue,
      light: '#80FFFF',
      dark: '#008B8B',
      contrastText: '#000000',
    },
    error: {
      main: matrixRed,
    },
    warning: {
      main: accentOrange,
    },
    info: {
      main: accentCobaltBlue,
    },
    success: {
      main: matrixGreen,
    },
    background: {
      default: matrixBlack,
      paper: '#0F0F0F',
    },
    text: {
      primary: matrixGreen,
      secondary: '#AAFFAA',
    },
  },
  typography: {
    fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
    h1: {
      textShadow: `0 0 10px ${matrixGreen}, 0 0 20px ${matrixGreen}`,
      letterSpacing: '0.05em',
    },
    h2: {
      textShadow: `0 0 8px ${matrixGreen}, 0 0 15px ${matrixGreen}`,
      letterSpacing: '0.05em',
    },
    h3: {
      textShadow: `0 0 6px ${matrixGreen}, 0 0 12px ${matrixGreen}`,
      letterSpacing: '0.05em',
    },
    h4: {
      textShadow: `0 0 4px ${matrixGreen}, 0 0 8px ${matrixGreen}`,
      letterSpacing: '0.05em',
    },
    h5: {
      textShadow: `0 0 3px ${matrixGreen}, 0 0 6px ${matrixGreen}`,
      letterSpacing: '0.05em',
    },
    h6: {
      textShadow: `0 0 2px ${matrixGreen}, 0 0 4px ${matrixGreen}`,
      letterSpacing: '0.05em',
    },
    body1: {
      letterSpacing: '0.03em',
    },
    body2: {
      letterSpacing: '0.03em',
    },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: `
        @keyframes scanline {
          0% {
            transform: translateX(-100%);
          }
          100% {
            transform: translateX(100%);
          }
        }
        
        @keyframes scan {
          0% {
            left: -100%;
          }
          100% {
            left: 100%;
          }
        }
        
        @keyframes pulse {
          0% {
            opacity: 0.6;
          }
          50% {
            opacity: 1;
          }
          100% {
            opacity: 0.6;
          }
        }
        
        @keyframes flicker {
          0% {
            opacity: 0.8;
          }
          5% {
            opacity: 0.5;
          }
          10% {
            opacity: 0.8;
          }
          15% {
            opacity: 0.9;
          }
          20% {
            opacity: 0.7;
          }
          25% {
            opacity: 0.8;
          }
          30% {
            opacity: 0.9;
          }
          35% {
            opacity: 0.7;
          }
          40% {
            opacity: 0.8;
          }
          45% {
            opacity: 0.9;
          }
          50% {
            opacity: 1;
          }
          55% {
            opacity: 0.9;
          }
          60% {
            opacity: 0.8;
          }
          65% {
            opacity: 0.7;
          }
          70% {
            opacity: 0.8;
          }
          75% {
            opacity: 0.9;
          }
          80% {
            opacity: 0.7;
          }
          85% {
            opacity: 0.8;
          }
          90% {
            opacity: 0.9;
          }
          95% {
            opacity: 0.7;
          }
          100% {
            opacity: 0.8;
          }
        }
        
        @keyframes colorShift {
          0% {
            filter: hue-rotate(0deg);
          }
          25% {
            filter: hue-rotate(15deg);
          }
          50% {
            filter: hue-rotate(0deg);
          }
          75% {
            filter: hue-rotate(-15deg);
          }
          100% {
            filter: hue-rotate(0deg);
          }
        }
        
        body {
          background: linear-gradient(to bottom, ${matrixBlack} 0%, #0A0A0A 100%);
          background-attachment: fixed;
          scrollbar-width: thin;
          scrollbar-color: ${matrixGreen} ${matrixBlack};
        }
        
        body:before {
          content: "";
          position: fixed;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          opacity: 0.05;
          z-index: -1;
          background-image: url("data:image/svg+xml,%3Csvg width='100%25' height='100%25' xmlns='http://www.w3.org/2000/svg'%3E%3Cdefs%3E%3Cpattern id='matrix' width='20' height='20' patternUnits='userSpaceOnUse'%3E%3Ctext x='0' y='15' font-size='10' fill='%2300FF41' opacity='0.2'%3E1%3C/text%3E%3Ctext x='10' y='10' font-size='10' fill='%2300FF41' opacity='0.2'%3E0%3C/text%3E%3C/pattern%3E%3C/defs%3E%3Crect width='100%25' height='100%25' fill='url(%23matrix)'/%3E%3C/svg%3E");
        }
        
        ::-webkit-scrollbar {
          width: 8px;
        }
        
        ::-webkit-scrollbar-track {
          background: ${matrixBlack};
        }
        
        ::-webkit-scrollbar-thumb {
          background-color: ${matrixDarkGreen};
          border-radius: 4px;
          border: 1px solid ${matrixGreen};
        }
        
        ::-webkit-scrollbar-thumb:hover {
          background-color: ${matrixGreen};
        }
      `,
    },
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundColor: 'rgba(10, 10, 10, 0.8)',
          backdropFilter: 'blur(5px)',
          border: `1px solid ${matrixDarkGreen}`,
          boxShadow: `0 0 15px rgba(0, 255, 65, 0.2), inset 0 0 10px rgba(0, 255, 65, 0.1)`,
          borderRadius: '4px',
          transition: 'all 0.3s ease',
          overflow: 'hidden',
          position: 'relative',
          '&:before': {
            content: '""',
            position: 'absolute',
            top: 0,
            left: 0,
            width: '100%',
            height: '2px',
            background: `linear-gradient(90deg, transparent, ${matrixGreen}, transparent)`,
            animation: 'scanline 2s linear infinite',
          },
          '&:after': {
            content: '""',
            position: 'absolute',
            top: 0,
            left: '-100%',
            width: '100%',
            height: '100%',
            background: `linear-gradient(90deg, transparent, rgba(0, 255, 65, 0.1), transparent)`,
            animation: 'scan 3s linear infinite',
          },
          '&:hover': {
            boxShadow: `0 0 20px rgba(0, 255, 65, 0.4), inset 0 0 15px rgba(0, 255, 65, 0.2)`,
            transform: 'translateY(-2px)',
          },
          '&:nth-of-type(3n+1)': {
            borderLeft: `2px solid ${accentOrange}`,
            '&::before': {
              background: `linear-gradient(90deg, ${accentOrange}, ${matrixGreen}, transparent)`,
            },
          },
          '&:nth-of-type(3n+2)': {
            borderRight: `2px solid ${accentCobaltBlue}`,
            '&::before': {
              background: `linear-gradient(90deg, transparent, ${matrixGreen}, ${accentCobaltBlue})`,
            },
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
          letterSpacing: '0.05em',
          border: `1px solid ${matrixDarkGreen}`,
          background: 'rgba(0, 20, 0, 0.7)',
          '&.MuiChip-colorSuccess': {
            background: `linear-gradient(to right, ${matrixDarkGreen}, rgba(0, 59, 0, 0.7))`,
            border: `1px solid ${matrixGreen}`,
            boxShadow: `0 0 5px ${matrixGreen}`,
          },
          '&.MuiChip-colorWarning': {
            background: 'linear-gradient(to right, rgba(58, 47, 11, 0.9), rgba(58, 47, 11, 0.7))',
            border: `1px solid ${accentOrange}`,
            boxShadow: `0 0 5px ${accentOrange}`,
            color: accentOrangeGlow,
          },
          '&.MuiChip-colorInfo': {
            background: 'linear-gradient(to right, rgba(0, 30, 71, 0.9), rgba(0, 30, 71, 0.7))',
            border: `1px solid ${accentCobaltBlue}`,
            boxShadow: `0 0 5px ${accentCobaltBlue}`,
            color: accentCobaltBlueGlow,
          },
          '&.MuiChip-colorError': {
            background: 'linear-gradient(to right, #3A0B0B, rgba(58, 11, 11, 0.7))',
            border: `1px solid ${matrixRed}`,
            boxShadow: `0 0 5px ${matrixRed}`,
          },
          '&.MuiChip-outlined': {
            background: 'transparent',
            border: `1px solid ${matrixDarkGreen}`,
            '&:hover': {
              boxShadow: `0 0 5px ${matrixGreen}`,
            },
          },
          '&:nth-of-type(3n+1)': {
            borderLeft: `2px solid ${accentOrange}`,
          },
          '&:nth-of-type(3n+2)': {
            borderRight: `2px solid ${accentCobaltBlue}`,
          },
        },
        label: {
          textShadow: `0 0 5px ${matrixGreen}`,
        },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: {
          fontFamily: '"Share Tech Mono", "Roboto Mono", monospace',
          letterSpacing: '0.05em',
          borderRadius: '2px',
          textTransform: 'uppercase',
          transition: 'all 0.3s ease',
          position: 'relative',
          overflow: 'hidden',
          '&:before': {
            content: '""',
            position: 'absolute',
            top: '-100%',
            left: 0,
            width: '100%',
            height: '100%',
            background: 'linear-gradient(rgba(255, 255, 255, 0.1), transparent)',
            transition: 'all 0.3s ease',
          },
          '&:hover': {
            '&:before': {
              top: '0',
            },
          },
          '&:nth-of-type(3n+1)': {
            '&::after': {
              content: '""',
              position: 'absolute',
              bottom: 0,
              left: 0,
              width: '100%',
              height: '2px',
              background: `linear-gradient(90deg, ${accentOrange}, transparent)`,
              opacity: 0.7,
            },
          },
          '&:nth-of-type(3n+2)': {
            '&::after': {
              content: '""',
              position: 'absolute',
              bottom: 0,
              right: 0,
              width: '100%',
              height: '2px',
              background: `linear-gradient(90deg, transparent, ${accentCobaltBlue})`,
              opacity: 0.7,
            },
          },
        },
        contained: {
          background: `linear-gradient(to right, ${matrixDarkGreen}, ${matrixCode})`,
          boxShadow: `0 0 10px ${matrixGreen}`,
          '&:hover': {
            background: `linear-gradient(to right, ${matrixCode}, ${matrixGreen})`,
            boxShadow: `0 0 15px ${matrixGreen}`,
          },
          '&.MuiButton-containedWarning': {
            background: `linear-gradient(to right, #3A2F0B, ${accentOrange})`,
            boxShadow: `0 0 10px ${accentOrange}`,
            '&:hover': {
              background: `linear-gradient(to right, ${accentOrange}, ${accentOrangeGlow})`,
              boxShadow: `0 0 15px ${accentOrange}`,
            },
          },
          '&.MuiButton-containedInfo': {
            background: `linear-gradient(to right, #001E47, ${accentCobaltBlue})`,
            boxShadow: `0 0 10px ${accentCobaltBlue}`,
            '&:hover': {
              background: `linear-gradient(to right, ${accentCobaltBlue}, ${accentCobaltBlueGlow})`,
              boxShadow: `0 0 15px ${accentCobaltBlue}`,
            },
          },
        },
        outlined: {
          borderColor: matrixGreen,
          color: matrixGreen,
          '&:hover': {
            borderColor: matrixGlow,
            boxShadow: `0 0 10px ${matrixGreen}`,
          },
          '&.MuiButton-outlinedWarning': {
            borderColor: accentOrange,
            color: accentOrange,
            '&:hover': {
              borderColor: accentOrangeGlow,
              boxShadow: `0 0 10px ${accentOrange}`,
            },
          },
          '&.MuiButton-outlinedInfo': {
            borderColor: accentCobaltBlue,
            color: accentCobaltBlueGlow,
            '&:hover': {
              borderColor: accentCobaltBlueGlow,
              boxShadow: `0 0 10px ${accentCobaltBlue}`,
            },
          },
        },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          color: matrixGreen,
          transition: 'all 0.3s ease',
          '&:hover': {
            backgroundColor: 'rgba(0, 255, 65, 0.1)',
            transform: 'scale(1.1)',
            boxShadow: `0 0 10px ${matrixGreen}`,
          },
          '&:nth-of-type(3n+1)': {
            color: accentOrange,
            '&:hover': {
              backgroundColor: 'rgba(255, 140, 0, 0.1)',
              boxShadow: `0 0 10px ${accentOrange}`,
            },
          },
          '&:nth-of-type(3n+2)': {
            color: accentCobaltBlueGlow,
            '&:hover': {
              backgroundColor: 'rgba(0, 71, 171, 0.1)',
              boxShadow: `0 0 10px ${accentCobaltBlue}`,
            },
          },
        },
      },
    },
    MuiTypography: {
      styleOverrides: {
        root: {
          letterSpacing: '0.03em',
          '&.MuiTypography-caption': {
            color: 'rgba(0, 255, 65, 0.7)',
          },
          '&:nth-of-type(5n+1) .MuiTypography-root': {
            textShadow: `0 0 3px ${accentOrange}`,
          },
          '&:nth-of-type(5n+3) .MuiTypography-root': {
            textShadow: `0 0 3px ${accentCobaltBlue}`,
          },
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          height: '4px',
          borderRadius: '2px',
          backgroundColor: matrixDarkGreen,
        },
        bar: {
          borderRadius: '2px',
          background: `linear-gradient(90deg, ${matrixDarkGreen}, ${matrixGreen}, ${matrixGlow})`,
          boxShadow: `0 0 5px ${matrixGreen}`,
          '&.MuiLinearProgress-barColorPrimary': {
            background: `linear-gradient(90deg, ${matrixDarkGreen}, ${matrixGreen}, ${matrixGlow})`,
          },
          '&.MuiLinearProgress-barColorSecondary': {
            background: `linear-gradient(90deg, #001E47, ${accentCobaltBlue}, ${accentCobaltBlueGlow})`,
          },
          '&.MuiLinearProgress-barColorWarning': {
            background: `linear-gradient(90deg, #3A2F0B, ${accentOrange}, ${accentOrangeGlow})`,
          },
        },
      },
    },
    MuiDivider: {
      styleOverrides: {
        root: {
          borderColor: matrixDarkGreen,
          '&:after, &:before': {
            borderColor: matrixDarkGreen,
          },
          '&:nth-of-type(3n+1)': {
            '&::after': {
              borderColor: accentOrange,
            },
          },
          '&:nth-of-type(3n+2)': {
            '&::before': {
              borderColor: accentCobaltBlue,
            },
          },
        },
      },
    },
  },
}); 