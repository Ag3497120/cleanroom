import CleanroomSite from '../cleanroom-site';
import '../cleanroom.css';
export default function Author(){return <CleanroomSite base={process.env.PAGES_BASE_PATH || ''} author/>;}
