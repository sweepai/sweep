import { useState, useRef } from "react"

export function ShowMore({ children }) {
    const [isExpanded, setIsExpanded] = useState(false);
    const [showButton, setShowButton] = useState(true);
    const contentRef = useRef(null);

    // sort this out later

    // useEffect(() => {
    //     console.log("contentRef", contentRef.current.scrollHeight)
    //     if (contentRef.current.scrollHeight < 200) {
    //         setShowButton(false);
    //     }
    // }, [contentRef]);

    const contentStyle = {
        overflow: 'hidden',
        transition: 'max-height 0.4s ease-in-out',
        maxHeight: (isExpanded || !showButton) ? '5000px' : '300px' // 1000px should be larger than the content's potential maximum height
    };

    return (
        <div>
            <div
                style={contentStyle}
                ref={contentRef}
            >
                {children}
            </div>
            {showButton && (
                <div style={{width: "100%", padding: 10, display: "flex", justifyContent: "center"}}>
                    <button onClick={() => setIsExpanded(!isExpanded)}>
                        {isExpanded ? 'Show Less' : 'Show More'}
                    </button>
                </div>
            )}
        </div>
    );
}
